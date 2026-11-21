"""Batch capsule APIs and scoped persistence. Storage keeps summary JSON opaque."""
from copy import deepcopy
import json
from script.util.errors import ContractError
from script.util.runtime import current, AGENT
from ...story import Operations
from ..common import business_context, writable, settings, identifier, scoped_sources
from .state import policy, metadata, project, groups
from .planning import plan, allocate


def require_enabled():
    if not settings()['capsule_mode']:
        raise ContractError('CAPSULE_DISABLED', 'Enable capsule_mode in creative configuration to use capsule APIs')


def auto_objects(repository, ctx):
    source = scoped_sources(repository)
    current_rows = source.local(ctx['node_id'])
    previous_rows = source.local(ctx['history_node_id']) if ctx['history_node_id'] != ctx['node_id'] else []
    previous_rows = [row for row in previous_rows if row['event']['seq'] <= ctx['history_event_seq']]
    packets = [row['event'] for row in current_rows if row['event']['event_type'] == 'director_packet']
    declared = packets[-1]['content'].get('capsule_object_ids', []) if packets else []
    if packets:
        from ..handoff import packet_refs
        current_rows += source.referenced(ctx, packet_refs(packets[-1]['content']))
    return list(dict.fromkeys([*declared, *(row['object_id'] for row in current_rows+previous_rows)]))


def load(repository, params):
    require_enabled()
    ctx = business_context(repository, params['node_id'], params.get('branch_id'))
    ids = params.get('object_ids')
    ids = list(dict.fromkeys(ids if ids is not None else auto_objects(repository, ctx)))
    objects = {value['object_id']: value for value in repository.records('object', {'object_id': ids})} if ids else {}
    if set(ids)-objects.keys():
        raise ContractError('NOT_FOUND', 'A requested capsule object does not exist')
    rows = scoped_sources(repository).sources(ctx['history_node_id'], ctx['node_id'], object_ids=ids,
                                                  seq_max=ctx['history_event_seq']) if ids else []
    return ctx, ids, objects, groups(rows)


def check(repository, params):
    ctx, ids, objects, rows = load(repository, params)
    return check_loaded(ctx,ids,objects,rows,params.get('view','jobs'))


def check_loaded(ctx,ids,objects,rows,view='jobs'):
    policies = {key: policy(objects[key]['object_type']) for key in ids}
    views = {key: project(rows.get(key, [])) for key in ids}
    plans = {key: plan(views[key], policies[key]) for key in ids if policies[key]['enabled']}
    chosen = allocate(plans, settings()['capsule']['max_batches_per_check'])
    result = []
    for key in ids:
        rules = policies[key]
        entry = {'object_id': key, 'enabled': rules['enabled'], 'policy': rules}
        for level in (1, 2):
            value = plans.get(key)
            batches = chosen.get((key, level), [])
            entry['level_'+str(level)] = {
                'pending_count': value['pending_counts'][level] if value else 0,
                'needs_summary': bool(value and (value['jobs'][level] or (level == 2 and value['blocked']))),
                'blocked_capsule_ids': value['blocked'] if value and level == 2 else [],
                'deferred_batch_count': len(value['jobs'][level])-len(batches) if value else 0,
                'batches': [{**batch, 'sources': [views[key]['rows'][source] for source in batch['source_event_ids']],
                             'target_characters': rules['level_'+str(level)+'_target_characters']}
                            for batch in batches]}
        result.append(entry)
    jobs=[entry for entry in result if any(entry['level_'+str(level)]['needs_summary'] or entry['level_'+str(level)]['blocked_capsule_ids'] or entry['level_'+str(level)]['deferred_batch_count'] for level in (1,2))]
    return {'scope':ctx,'branch_id':ctx['branch_id'],'capsule_mode':True,'view':view,
            'objects':result if view=='full' else jobs,'checked_count':len(ids),'idle_count':len(ids)-len(jobs),
            'deferred_batch_count':sum(entry['level_'+str(level)]['deferred_batch_count'] for entry in result for level in (1,2))}


def read(repository, params):
    ctx, ids, objects, rows = load(repository, params)
    result = []
    for key in ids:
        view = project(rows.get(key, []))
        rules = policy(objects[key]['object_type'])
        result.append({'object_id': key, 'enabled': rules['enabled'],
                       'overview': view['overview'] if rules['enabled'] else [],
                       'history': view['views'] if params.get('include_history', False) else []})
    return {'scope': ctx, 'branch_id': ctx['branch_id'], 'capsule_mode': True, 'objects': result}


def validate_record(obj, event, rows):
    current().validator.validate(event['content'], {'$ref': AGENT['$id']+'#/definitions/capsule_event_content'})
    rules = policy(obj['object_type'])
    if not rules['enabled']:
        raise ContractError('CAPSULE_OBJECT_DISABLED', 'Capsules are disabled for this object category')
    if event['event_type'] not in settings()['categories'][rules['kind']]['event_types']:
        raise ContractError('INVALID_CAPSULE', 'Capsule event type must belong to its object category')
    meta = metadata(event)
    view = project(rows)
    if not meta['source_event_ids'] and not meta['supersedes_capsule_event_ids']:
        raise ContractError('INVALID_CAPSULE', 'An empty capsule must retire an existing summary version')
    for source in meta['source_event_ids']:
        row = view['rows'].get(source)
        if row is None or row['object_id'] != obj['object_id']:
            raise ContractError('SOURCE_NOT_VISIBLE', 'Capsule sources must be visible records of the same object')
        if meta['level'] == 1:
            usable = source in view['contents']
        else:
            usable = source in view['capsules'] and metadata(row['event'])['level'] == 1 and view['statuses'][source]['status'] == 'valid'
        if not usable:
            raise ContractError('INVALID_CAPSULE', 'Capsule source is not currently usable at the requested level')
    for old in meta['supersedes_capsule_event_ids']:
        row = view['capsules'].get(old)
        if row is None or metadata(row['event'])['level'] != meta['level'] or view['statuses'][old]['status'] == 'superseded':
            raise ContractError('INVALID_CAPSULE', 'A superseded capsule must be a visible current version at the same level')
    # Different batches do not silently double-cover the same sources.
    sources = set(meta['source_event_ids'])
    for key, row in view['capsules'].items():
        if key in meta['supersedes_capsule_event_ids'] or view['statuses'][key]['status'] != 'valid':
            continue
        if metadata(row['event'])['level'] == meta['level'] and sources.intersection(metadata(row['event'])['source_event_ids']):
            raise ContractError('INVALID_CAPSULE', 'Overlapping summary versions require an explicit supersedes capsule ID')


def validate_event(repository, node_id, object_id, event, branch_id):
    require_enabled()
    ctx = business_context(repository, node_id, branch_id)
    obj = repository.require('object', object_id)
    rows = scoped_sources(repository).sources(ctx['history_node_id'], ctx['node_id'], object_ids=[object_id],
                                                  seq_max=ctx['history_event_seq'])
    validate_record(obj, event, rows)


def save(repository, params):
    require_enabled()
    entries = params['content']['capsules']
    ids = list(dict.fromkeys(entry['object_id'] for entry in entries))
    # One object lookup and one composed source query for the whole request.
    with repository.transaction():
        ctx, _, objects, rows = load(repository, {**params, 'object_ids': ids})
        node = repository.require('node', ctx['node_id'])
        from ..common import in_maintenance
        if not in_maintenance(ctx):Operations(repository)._leaf_branch(ctx['node_id'], ctx['branch_id'])
        receipts = []
        writing_started = False
        for entry in entries:
            obj = objects[entry['object_id']]
            if not policy(obj['object_type'])['enabled']:
                raise ContractError('CAPSULE_OBJECT_DISABLED', 'Capsules are disabled for this object category')
            content = deepcopy(entry['content'])
            if '_capsule' in content:
                raise ContractError('INVALID_CAPSULE', 'Capsule metadata is generated from the entry controls')
            content['_capsule'] = {'level': entry['level'], 'source_event_ids': entry['source_event_ids'],
                                   'supersedes_capsule_event_ids': entry.get('supersedes_capsule_event_ids', [])}
            if in_maintenance(ctx) and ctx.get('maintenance_job_id'):
                content['_capsule']['maintenance_job_id']=ctx['maintenance_job_id']
            fingerprint = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            event = {'event_id': identifier('capsule', ctx['node_id'], obj['object_id'], fingerprint),
                     'event_type': settings()['categories'][policy(obj['object_type'])['kind']]['event_types'][0],
                     'type_name': obj['object_key'], 'event_action': 'summarize', 'content': content}
            old = next((row for row in rows.get(obj['object_id'], []) if row['event']['event_id'] == event['event_id']), None)
            if old:
                if old['node_id'] != ctx['node_id'] or old['event']['content'] != content:
                    raise ContractError('IDEMPOTENCY_CONFLICT', 'Capsule retry must keep its original identity and content')
                receipts.append({'object_id': obj['object_id'], 'event_id': event['event_id'], 'level': entry['level'], 'already_exists': True})
                continue
            validate_record(obj, event, rows.get(obj['object_id'], []))
            if not writing_started:
                if node['state'] == 'active':
                    repository.update('node', ctx['node_id'], {'state': 'updating'})
                writable(repository, ctx)
                writing_started = True
            result = repository.append_event(ctx['node_id'], obj['object_id'], event)
            rows.setdefault(obj['object_id'], []).append({'event': result['event'], 'node_id': ctx['node_id'], 'object_id': obj['object_id']})
            receipts.append({'object_id': obj['object_id'], 'event_id': event['event_id'], 'level': entry['level'], 'already_exists': False})
        if writing_started and node['state'] == 'active':
            repository.update('node', ctx['node_id'], {'state': 'active'})
        result = {'scope': ctx, 'branch_id': ctx['branch_id'], 'capsule_mode': True, 'capsules': receipts}
        if params.get('include_next_jobs',True):
            result['next_jobs']=check_loaded(ctx,ids,objects,rows)
        current().validator.validate(result, {'$ref': AGENT['$id']+'#/definitions/result_capsule_save'})
    return result
