"""Initialize a world and its root. Content design remains with the director."""
from copy import deepcopy
import hashlib
from .creative.common import workflow_object
from script.util.contracts import ContractError, AGENT, validate
from script.workflow.data.story_stores import StoryStores
from .story import Operations


ROOT_ID = 'node-root'
MAIN_ID = 'main'


class StoryInitializer:
    def __init__(self, stores: StoryStores):
        self.stores = stores

    @staticmethod
    def _records(params: dict, settings: dict) -> list[tuple[dict, dict]]:
        story_id = params['story_id']
        records = [(
            {'object_id': 'story', 'object_type': 'story', 'object_key': story_id, 'name': params['title']},
            {'event_id': 'init-story', 'event_type': 'story_identity', 'type_name': 'identity',
             'content': {'story_id': story_id, 'title': params['title']}},
        )]
        for key, content in sorted(settings.items()):
            suffix = hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]
            records.append((
                {'object_id': 'story_setting_' + key, 'object_type': 'story_setting', 'object_key': key, 'name': key},
                {'event_id': 'init-setting-' + suffix, 'event_type': 'story_setting', 'type_name': key, 'content': content},
            ))
        for ordinal, message in enumerate(params['content']['raw_user_messages'], start=1):
            records.append((
                workflow_object('user_input', 'initialization'),
                {'event_id': f'init-input-{ordinal:04d}', 'event_type': 'user_input', 'type_name': 'initialization',
                 'content': {**deepcopy(message), 'source': message.get('source', AGENT['definitions']['raw_input_message']['properties']['source']['default']), 'ordinal': ordinal}},
            ))
        return records

    @staticmethod
    def _same_initialization(repository, records: list[tuple[dict, dict]]) -> bool:
        expected_ids = {event['event_id'] for _, event in records}
        # Compare the immutable initialization request, not a later story state projection.
        initial = repository.node_events(ROOT_ID, limit=1000)
        actual = {event['event_id']: event for event in initial['items'] if event['event_id'].startswith('init-')}
        if initial['next_offset'] is not None:
            offset = initial['next_offset']
            while offset is not None:
                page = repository.node_events(ROOT_ID, limit=1000, offset=offset)
                actual.update((event['event_id'], event) for event in page['items'] if event['event_id'].startswith('init-'))
                offset = page['next_offset']
        if set(actual) != expected_ids:
            return False
        for _, event in records:
            stored = deepcopy(actual[event['event_id']])
            if stored is not None and event['event_type']=='story_identity':
                stored['content'].pop('skill_version',None)
            if stored is None or any(stored[key] != value for key, value in event.items()):
                return False
        return True

    def initialize(self, params: dict) -> dict:
        settings = deepcopy(params['content']['settings'])
        from script.initialize import read_preferences
        from script.util.runtime import current
        profile = read_preferences(current().project_root) or {}
        for key in ('protagonist', 'narration'):
            if key not in settings and profile.get(key) is not None:
                settings[key] = deepcopy(profile[key])
        records = self._records(params, settings)
        environment = params.get('environment', AGENT['definitions']['story_init_params']['properties']['environment']['default'])
        repository, location = self.stores.provision(params['story_id'], environment)
        try:
            with repository.transaction():
                root = repository.get('node', ROOT_ID)
                already_initialized = root is not None
                if root is not None:
                    if root['node_type'] != 'root' or root['state'] != 'active' or not self._same_initialization(repository, records):
                        raise ContractError('STORY_EXISTS', 'This story ID already has different initialization content')
                else:
                    if any(repository.info()['counts'].values()):
                        raise ContractError('STORY_EXISTS', 'Storage already contains records from another initialization')
                    operations = Operations(repository)
                    operations.begin({'node_id': ROOT_ID, 'node_type': 'root', 'branch_id': MAIN_ID})
                    for obj, event in records:
                        operations.create_event({'node_id': ROOT_ID, 'branch_id': MAIN_ID, 'object': obj, 'event': event})
                    operations.publish(ROOT_ID, MAIN_ID)
                result = {
                    'story_id': params['story_id'], 'title': params['title'], 'environment': environment,
                    **location, 'root_node_id': ROOT_ID, 'branch_id': MAIN_ID,
                    'status': 'initialized', 'already_initialized': already_initialized, 'settings': settings,
                    'counts': repository.info()['counts'],
                    'next_scene': {'operation': 'scene_next', 'implemented': True},
                }
                validate(result, 'story_initialization', AGENT)
                return result
        finally:
            repository.close()
