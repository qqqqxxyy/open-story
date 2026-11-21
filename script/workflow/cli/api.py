"""Workflow application with central execution logs; no reverse CLI imports."""
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from script.data.api import connect
from script.util.runtime import current, using, AGENT
from script.util.contracts import validate
from script.util.errors import ContractError
from script.util.logging import StoryLogger, parameter_summary, result_summary
from script.workflow.data.repositories import Repository
from script.workflow.dispatch import dispatch, operation


class Application:
    def __init__(self, config_path=None, data_root=None, resources=None, log_level=None):
        self.resources = resources or current()
        self.config_path = config_path
        self.data_root = Path(data_root) if data_root is not None else self.resources.project_root / 'story-data'
        self._data_root_explicit = data_root is not None
        self._repository = None
        source = self.resources.logger
        if source is None:
            cfg = self.resources.settings['logging']
            self.logger = StoryLogger(self.resources.project_root/cfg['default_path'], log_level or cfg['level'],
                                      cfg['filename'], cfg['lock_timeout_seconds'], cfg['rotation_days'])
        else:
            self.logger = StoryLogger(source.default_path, log_level or source.level, source.filename,
                                      source.lock_timeout_seconds, source.rotation_days)
        self.invocation_id = uuid4().hex
        self._calls = []
        self._database_id = None

    def _log_fields(self, params=None):
        params = params if isinstance(params, dict) else {}
        fields = {'invocation_id': self.invocation_id}
        if self._calls:
            fields.update(self._calls[-1])
        if params.get('branch_id'):
            fields['branch_id'] = params['branch_id']
        database = self._database_id or params.get('database_id') or params.get('story_id')
        if database:
            fields['database_id'] = database
        return fields

    def trace(self, message, **fields):
        self.logger.debug(message, **{**self._log_fields(), **fields})

    @property
    def repository(self):
        if self._repository is None:
            if self.config_path is None:
                raise ContractError('CONFIG_REQUIRED', 'This operation requires --config')
            self.trace('storage.connect.started', function='script.data.api:connect')
            with using(self.resources):
                self._repository = Repository(connect(self.config_path))
                self._database_id = self._repository.identity()['database_id']
            self.trace('storage.connect.completed', function='script.data.api:connect')
        return self._repository

    def execute(self, request):
        with using(self.resources):
            name = request.get('operation', 'unknown') if isinstance(request, dict) else 'unknown'
            params = request.get('params', {}) if isinstance(request, dict) else {}
            parent = self._calls[-1]['call_id'] if self._calls else None
            frame = {'operation': name, 'call_id': uuid4().hex, 'phase': 'request_validation'}
            if parent:
                frame['parent_call_id'] = parent
            if isinstance(params, dict):
                for key in ('branch_id',):
                    if params.get(key): frame[key] = params[key]
            self._calls.append(frame)
            started = perf_counter()
            self.logger.info('operation.started', **self._log_fields(params), params=parameter_summary(params))
            try:
                validate(request, 'request', AGENT)
                frame['phase'] = 'operation_lookup'
                entry = operation(self.resources, name)
                frame['phase'] = 'configuration_validation'
                mode = entry['storage_mode']
                if mode == 'initialize' and self.config_path is not None:
                    raise ContractError('INVALID_CONFIG', 'Initialization creates its own config; omit --config')
                if mode == 'existing' and self._data_root_explicit:
                    raise ContractError('INVALID_CONFIG', '--data-root is only for initialization/reserved operations')
                self.trace('dispatch.selected', function=entry['handler'])
                result = dispatch(self, name, request['params'])
                if isinstance(result, dict) and (result.get('database_id') or result.get('story_id')):
                    self._database_id = result.get('database_id') or result['story_id']
                frame['phase'] = 'completed'
                completed_fields = self._log_fields(params)
                if isinstance(result, dict):
                    scope = result.get('scope')
                    branch = result.get('branch_id') or (scope.get('branch_id') if isinstance(scope, dict) else None)
                    if branch:
                        completed_fields['branch_id'] = branch
                self.logger.info('operation.completed', **completed_fields,
                                 duration_ms=round((perf_counter() - started) * 1000, 3),
                                 result=result_summary(result))
                return result
            except Exception as exc:
                meta = getattr(exc, 'definition', self.resources.errors.get(getattr(exc, 'code', 'OPERATION_FAILED'), {}))
                self.logger.log(meta.get('log_level', 'error'), 'operation.failed', **self._log_fields(params),
                                duration_ms=round((perf_counter() - started) * 1000, 3),
                                code=getattr(exc, 'code', 'OPERATION_FAILED'), error=str(exc))
                if self.logger.level == 'debug':
                    import traceback
                    self.trace('exception.detail', traceback=traceback.format_exc())
                raise
            finally:
                self._calls.pop()

    def log_response_metrics(self, response, params=None, **metrics):
        fields = self._log_fields(params)
        fields['operation'] = response['operation']
        data = response.get('data')
        if isinstance(data, dict) and isinstance(data.get('scope'), dict):
            branch = data['scope'].get('branch_id')
            if branch:
                fields['branch_id'] = branch
        self.logger.info('response.serialized', **fields, ok=response['ok'], **metrics)

    def close(self):
        if self._repository is not None:
            self._repository.close()
            self._repository = None
