"""The script configuration composition root. conf itself is declarative only."""
import json
from pathlib import Path
from functools import lru_cache
from script.util.contracts import SchemaValidator
from script.util.errors import ContractError
from script.util.logging import StoryLogger, LEVELS
from script.util.runtime import RuntimeResources, install
from script.util.versioning import version_policy

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

@lru_cache(maxsize=None)
def _load(conf_path, project_root, logging_enabled):
    conf = Path(conf_path)
    root = Path(project_root)
    try:
        settings = _read(conf/'runtime.json')
        version_policy(settings)
        settings['cli']['description'] = settings['cli']['description'].format(skill_version=settings['skill_version'])
        schemas = {name:_read(conf/filename) for name,filename in settings['schemas'].items()}
        validator = SchemaValidator(schemas)
        settings['creative'] = _read(conf/settings['creative_config'])
        creative=settings['creative']
        validator.validate(creative['workflow_objects'], {'$ref': schemas['workflow']['$id']+'#/definitions/workflow_objects'})
        if not isinstance(creative['capsule_mode'],bool):raise ValueError('capsule_mode must be boolean')
        validator.validate(creative['capsule'], {'$ref': schemas['workflow']['$id']+'#/definitions/capsule_config'})
        validator.validate(creative['reading'], {'$ref': schemas['workflow']['$id']+'#/definitions/reading_config'})
        if set(creative['capsule']['kinds'])-set(creative['categories']):raise ValueError('Unknown capsule category override')
        for key,value in creative['recall'].items():
            if key!='gram_widths' and (not isinstance(value,int) or value<0):raise ValueError('Recall parameters must be nonnegative integers: '+key)
        for category in creative['categories'].values():
            if category.get('schema'):validator.resolve(category['schema'])
        public_kinds=set(validator.resolve({'$ref':schemas['agent']['$id']+'#/definitions/business_kind'})['enum'])
        if public_kinds!=set(creative['categories']):raise ValueError('Business schema kinds and creative categories differ')
        content_rules=schemas['agent']['definitions']['operation_business_save']['allOf']
        rules={}
        for item in content_rules:
            conditions=item['if'].get('allOf',[item['if']])
            kind=next((c.get('properties',{}).get('kind',{}).get('const') for c in conditions if 'kind' in c.get('properties',{})),None)
            if kind is not None:rules[kind]=item['then']['properties']['content']
        for name,category in creative['categories'].items():
            if category.get('schema') and rules.get(name)!=category['schema']:raise ValueError('Content schema reference differs: '+name)
        operations = {}
        cli_names = set()
        for entry in _read(conf/settings['operations'])['operations']:
            operation = entry['operation']
            if operation in operations or entry['cli_name'] in cli_names:
                raise ValueError('Operation and CLI names must be unique')
            if entry['storage_mode'] not in ('initialize','existing','reserved','library'):
                raise ValueError('Unknown storage mode: '+entry['storage_mode'])
            # Validate references without importing workflow handlers during startup.
            validator.resolve(entry['input_schema'])
            validator.resolve(entry['output_schema'])
            if not entry['handler'].startswith('script.workflow.pipeline.') or ':' not in entry['handler']:
                raise ValueError('Handler must name a workflow pipeline function')
            flags = set()
            for binding in entry['bindings']:
                if binding['kind'] not in ('value','json_file','filters'):
                    raise ValueError('Unknown binding kind')
                if binding['flag'] in flags:
                    raise ValueError('Duplicate binding flag')
                flags.add(binding['flag'])
                if 'schema' in binding:
                    validator.resolve(binding['schema'])
            operations[operation] = entry
            cli_names.add(entry['cli_name'])
        errors = _read(conf/settings['errors'])['codes']
        logging = settings['logging']
        if logging['level'] not in LEVELS:
            raise ValueError('Unknown log level')
        if any(entry['log_level'] not in LEVELS for entry in errors.values()):
            raise ValueError('Unknown error log level')
        if isinstance(logging['rotation_days'], bool) or not isinstance(logging['rotation_days'], int) or logging['rotation_days'] <= 0:
            raise ValueError('logging.rotation_days must be a positive integer')
        logger = (StoryLogger(root/logging['default_path'], logging['level'], logging['filename'],
                              logging['lock_timeout_seconds'], logging['rotation_days']) if logging_enabled else None)
        return RuntimeResources(root, settings, schemas, _read(conf/settings['relation_rules']), operations, errors, validator, logger)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ContractError('CONFIGURATION_ERROR', 'Script configuration load failed: '+str(exc)) from exc

def bootstrap(conf_path=None, project_root=None, *, logging_enabled=True):
    """Also available to programmatic callers; lower layers never call this function."""
    root = Path(project_root).resolve() if project_root is not None else PROJECT_ROOT
    conf = Path(conf_path).resolve() if conf_path is not None else PROJECT_ROOT/'script/conf'
    return install(_load(str(conf), str(root), logging_enabled))
