"""Path-ordered explicit event actions, applied before bounded creative selection."""
import json
from .common import settings, get_path
from .actions import unpack, supported


def category(row):
    for name, definition in settings()['categories'].items():
        if row['event']['event_type'] in definition['event_types']: return name
    return None


def identity(row, definition):
    value, _ = unpack(row['event']['content'])
    if isinstance(value, str) and definition.get('identity_paths'): return value
    for path in definition.get('identity_paths', []):
        key = get_path(value, path)
        if isinstance(key, str) and key: return key
    return row['object_id']


def project(rows):
    result = {key: [] for key in settings()['categories']}
    views = {}
    excluded = set()
    for row in rows:
        event = row['event']
        if event['state'] != 'active' or event['event_action'] == 'summarize': continue
        name = category(row)
        if name is None: continue
        action = event['event_action']
        supported(action)
        content, targets = unpack(event['content'])
        if action in ('replace', 'cancel'):
            excluded.update(targets)
        if action == 'cancel': continue
        # Replacement links are dependencies, not adopted literary source material.
        views[event['event_id']] = (name, {**row, 'event': {**event, 'content': content},
                                        'source_event_ids': [event['event_id']]})
    for event_id, (name, view) in views.items():
        if event_id not in excluded:
            result[name].append(view)
    return result


def searchable(row):
    definition = settings()['categories'].get(category(row), {})
    value, _ = unpack(row['event']['content'])
    parts = [get_path(value, key) for key in definition.get('text_paths', [])]
    if not any(part is not None for part in parts): return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return ' '.join(part if isinstance(part, str) else json.dumps(part, ensure_ascii=False)
                    for part in parts if part is not None)
