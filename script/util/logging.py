"""Central JSONL logs, append locking and instance-time rotation."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4
from filelock import FileLock

LEVELS = {'debug': 10, 'info': 20, 'warn': 30, 'error': 40}


class StoryLogger:
    def __init__(self, default_path, level='info', filename='runtime.log',
                 lock_timeout_seconds=5, rotation_days=7):
        self.default_path = Path(default_path)
        self.level = level
        self.filename = filename
        self.lock_timeout_seconds = lock_timeout_seconds
        self.rotation_days = rotation_days
        self._check_rotation()

    def _check_rotation(self):
        filename = self.default_path / self.filename
        if not filename.exists():
            return
        try:
            with FileLock(str(filename) + '.lock', timeout=self.lock_timeout_seconds):
                if not filename.exists() or filename.stat().st_size == 0:
                    return
                with filename.open(encoding='utf-8') as stream:
                    first = json.loads(stream.readline())
                started = datetime.fromisoformat(first['time'])
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if now - started >= timedelta(days=self.rotation_days):
                    stamp = now.strftime('%Y%m%dT%H%M%S%fZ')
                    archive = filename.with_name(filename.stem + '.' + stamp + '.' + uuid4().hex[:8] + filename.suffix)
                    filename.rename(archive)
        except Exception as exc:
            self._failure(exc)

    @staticmethod
    def _failure(exc):
        print('OpenStory log write failed: ' + str(exc), file=sys.stderr)

    def log(self, level, message, **fields):
        if LEVELS[level] < LEVELS[self.level]:
            return
        try:
            self.default_path.mkdir(parents=True, exist_ok=True)
            filename = self.default_path / self.filename
            record = {'time': datetime.now(timezone.utc).isoformat(), 'level': level,
                      'message': message, **fields}
            line = json.dumps(record, ensure_ascii=False, default=str) + '\n'
            with FileLock(str(filename) + '.lock', timeout=self.lock_timeout_seconds):
                with filename.open('a', encoding='utf-8', newline='') as stream:
                    stream.write(line)
                    stream.flush()
        except Exception as exc:
            # Logging cannot relabel an already committed database operation.
            self._failure(exc)

    def debug(self, message, **fields): self.log('debug', message, **fields)
    def info(self, message, **fields): self.log('info', message, **fields)
    def warn(self, message, **fields): self.log('warn', message, **fields)
    def error(self, message, **fields): self.log('error', message, **fields)


def parameter_summary(params):
    """Control values only; never serialize content, prose or command bodies."""
    if not isinstance(params, dict):
        return {}
    result = {key: value for key, value in params.items()
              if key != 'story_id' and (isinstance(value, (str, int, float, bool)) or value is None)}
    if params.get('story_id') and 'database_id' not in result:
        result['database_id'] = params['story_id']
    for key in ('object_ids', 'event_ids', 'event_types', 'character_ids', 'fields', 'source_event_ids', 'source_node_ids'):
        if isinstance(params.get(key), list):
            result[key] = params[key]
    for key in ('content', 'patch', 'filters'):
        if isinstance(params.get(key), dict):
            result[key + '_keys'] = list(params[key])
    if isinstance(params.get('commands'), list):
        result['command_count'] = len(params['commands'])
    for key in ('event', 'object', 'record'):
        if isinstance(params.get(key), dict):
            result[key] = identifiers(params[key])
    return result


def identifiers(value):
    result = {key: item for key, item in value.items()
              if key != 'story_id' and (key.endswith('_id') or key in ('state', 'status', 'backend', 'entity', 'select_as'))
              and isinstance(item, (str, int, bool, type(None)))}
    if value.get('story_id') and 'database_id' not in result:
        result['database_id'] = value['story_id']
    return result


def result_summary(result):
    if isinstance(result, list):
        return {'result_count': len(result)}
    if not isinstance(result, dict):
        return {'result_type': type(result).__name__}
    summary = identifiers(result)
    for key in ('counts', 'already_exists', 'already_initialized', 'total', 'next_offset',
                'deleted_events', 'deleted_relations', 'snapshot_available', 'html_available',
                'publication_status','snapshot_changed','checked_count','idle_count','deferred_batch_count','next_operation','next_action','complete'):
        if key in result:
            summary[key] = result[key]
    for key in ('node', 'event', 'object', 'branch', 'head', 'ownership', 'author', 'scene', 'attempt', 'accepted_predecessor', 'next_job'):
        if isinstance(result.get(key), dict):
            summary[key] = identifiers(result[key])
    for key in ('items', 'node_ids', 'sources', 'events', 'objects', 'capsules', 'narratives'):
        if isinstance(result.get(key), list):
            summary[key + '_count'] = len(result[key])
    if isinstance(result.get('scope'), dict):
        summary['scope'] = {key: result['scope'][key] for key in
                            ('node_id', 'branch_id', 'history_node_id', 'history_event_seq', 'at_node_id', 'seq_max')
                            if key in result['scope']}
    for key in ('selected_character_ids', 'selection_diagnostics'):
        if key in result:
            summary[key] = result[key]
    if 'view' in result:
        summary['view'] = result['view']
    if isinstance(result.get('page'), dict):
        summary['page'] = result['page']
    if isinstance(result.get('narratives'), list):
        summary['narrative_node_ids'] = [item['node_id'] for item in result['narratives']]
        summary['narrative_event_ids'] = [item['narrative_event_id'] for item in result['narratives']]
        summary['narrative_characters'] = sum(len(item.get('literary_text') or '')
                                             for item in result['narratives'])
    if isinstance(result.get('literary_text'), str):
        summary['narrative_characters'] = len(result['literary_text'])
    if isinstance(result.get('capsules'), list) and all('event_id' in item for item in result['capsules']):
        summary['capsule_receipts'] = [{**identifiers(item), 'level': item['level'], 'already_exists': item['already_exists']}
                                       for item in result['capsules']]
    return summary
