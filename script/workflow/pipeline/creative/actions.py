"""Explicit per-event actions. Storage keeps JSON opaque; these rules belong to workflow."""
from copy import deepcopy
from script.util.errors import ContractError
from script.util.contracts import validate
from script.util.runtime import AGENT


def unpack(content):
    if isinstance(content, dict) and isinstance(content.get('_control'), dict) and 'payload' in content:
        return content['payload'], content['_control'].get('target_event_ids', [])
    return content, []


def package(content, targets=(), sources=()):
    value = {'payload': deepcopy(content), '_control': {'target_event_ids': list(targets)}}
    if sources:
        value['source_event_ids'] = list(sources)
    validate(value, 'business_record_envelope', AGENT)
    return value


def supported(action):
    if action == 'summarize':
        from .capsule.service import require_enabled
        require_enabled()


def from_request(params):
    """Low-level CLI controls become one authoritative stored JSON representation."""
    value = deepcopy(params)
    event = value['event']
    action = event.setdefault('event_action', 'append')
    supported(action)
    targets = value.pop('target_event_ids', [])
    if action in ('replace', 'cancel') or targets:
        event['content'] = package(event.get('content', {}), targets)
    return value


def validate_event(repository, node_id, object_id, event, branch_id):
    action = event.get('event_action', 'append')
    supported(action)
    if action == 'summarize':
        from .capsule import validate_event
        validate_event(repository, node_id, object_id, event, branch_id)
        return []
    payload, targets = unpack(event['content'])
    if isinstance(event['content'], dict) and '_control' in event['content']:
        validate(event['content'], 'business_record_envelope', AGENT)
    if action == 'append':
        if targets:
            raise ContractError('INVALID_EVENT_ACTION', 'append does not target existing events')
        return targets
    if not targets:
        raise ContractError('INVALID_EVENT_ACTION', 'replace/cancel needs nonempty target-event-ids')
    if action == 'cancel' and not isinstance(payload, dict):
        raise ContractError('INVALID_EVENT_ACTION', 'cancel payload is an optional reason object')
    from .common import business_context
    from script.workflow.data.creative import CreativeRepository
    ctx = business_context(repository, node_id, branch_id)
    rows = CreativeRepository(repository).referenced(ctx, targets)
    for row in rows:
        target = row['event']
        if row['object_id'] != object_id or target['event_id'] == event['event_id']:
            raise ContractError('INVALID_EVENT_ACTION_TARGET', 'Targets must be earlier records of the same object')
        if target['state'] != 'active' or target['event_action'] not in ('append', 'replace'):
            raise ContractError('INVALID_EVENT_ACTION_TARGET', 'Only stored active append/replace content records can be targeted')
    return targets


def register_targets(repository, event_id, targets):
    from hashlib import sha256
    for target in targets:
        repository.create('relation', {
            'relation_id': 'action-' + sha256((event_id+'\0'+target).encode()).hexdigest()[:32],
            'relation_type': 'event_action_target', 'key_type': 'event', 'key_id': event_id,
            'target_event_id': target})
