"""Append business records, choose adopted design versions, and finalize actual changes."""
from copy import deepcopy
from script.util.errors import ContractError
from ..story import Operations
from .common import enabled, context, writable, append, validate_content, settings, identifier, latest, business_context, messages, workflow_object, scoped_sources
from .projection import project, identity
from .actions import package, supported


def stored_content(value):
    kind = value['kind']
    content = deepcopy(value.get('content', {}))
    if kind == 'user_input' and value.get('event_action', 'append') != 'cancel':
        content={**content,'raw_user_messages':messages(content)}
    return package(content, value.get('target_event_ids', []), value.get('source_event_ids', []))



def save_record(repository, ctx, value, event_id=None):
    kind = value['kind']
    action = value.get('event_action', 'append')
    supported(action)
    if action == 'summarize':
        raise ContractError('USE_CAPSULE_SAVE', 'Use capsule-save for summary content and generated metadata')
    if action != 'cancel':
        validate_content(kind, value['content'])
    content = stored_content(value)
    refs = value.get('source_event_ids', [])
    sources = scoped_sources(repository)
    sources.referenced(ctx, refs)
    event = append(repository, ctx, kind, value['key'], content, event_id, value.get('name'), event_action=action)
    return event


def save(repository, params):
    enabled()
    ctx = business_context(repository, params['node_id'], params.get('branch_id'))
    node = repository.require('node', ctx['node_id'])
    with repository.transaction():
        if node['state'] == 'active':
            repository.update('node', ctx['node_id'], {'state': 'updating'})
        else:
            writable(repository, ctx)
        event = save_record(repository, ctx, params, params.get('event_id'))
        if node['state'] == 'active':
            repository.update('node', ctx['node_id'], {'state': 'active'})
    object_id = repository.owner(event['event_id'])['object_id'] if params.get('event_id') else kind_id(params['kind'], params['key'])
    return {'event': event, 'object_id': object_id}


def kind_id(kind, key):
    return workflow_object(kind, key)['object_id']


def read_records(repository, params):
    enabled()
    ctx = business_context(repository, params['node_id'], params.get('branch_id'))
    kinds = settings()['categories'][params['kind']]['event_types']
    rows = scoped_sources(repository).sources(ctx['history_node_id'], ctx['node_id'], event_types=kinds,
        seq_max=ctx['history_event_seq'])
    if params.get('key'):
        key=params['key']
        aliases={kind_id(kind,key) for kind in kinds}|{kind_id(params['kind'],key)}
        definition=settings()['categories'][params['kind']]
        if params['kind'] in settings()['workflow_objects']:
            rows=[row for row in rows if row['event']['type_name']==key]
        else:
            rows=[row for row in rows if row['object_id'] in aliases or identity(row,definition)==key]
    current = project(rows)[params['kind']]
    return {'scope': ctx, 'current': current, 'history': rows if params.get('include_history', False) else []}


def archive(repository, params):
    enabled()
    from .common import in_maintenance
    from . import manuscripts
    ctx=context(repository,params['node_id'],params.get('branch_id'))
    node=repository.require('node',ctx['node_id'])
    params=deepcopy(params)
    defaults=params['content'].get('default_source_event_ids',[])
    entries=[{**v,'source_event_ids':v.get('source_event_ids',defaults)} for v in params['content']['events']]
    prior=latest(repository,ctx['node_id'],'director_archive')
    if prior:
        if len(prior['content']['event_ids'])!=len(entries):
            raise ContractError('IDEMPOTENCY_CONFLICT','Archive retry must preserve the complete batch')
        for event_id,value in zip(prior['content']['event_ids'],entries):
            old=repository.require('event',event_id)
            if old['content']!=stored_content(value) or old['event_type']!=value['kind'] or old['type_name']!=value['key'] or old['event_action']!=value.get('event_action','append'):
                raise ContractError('IDEMPOTENCY_CONFLICT','Archive retry must keep its original records')
    else:
        if manuscripts.attempt(repository,ctx['node_id']) and not in_maintenance(ctx):
            raise ContractError('MAINTENANCE_SCOPE','Use the adopted manuscript maintenance job')
        if latest(repository,ctx['node_id'],'display_metadata') is None:
            raise ContractError('DISPLAY_REQUIRED','Display prose before semantic archival')
        with repository.transaction():
            if node['state']=='active':repository.update('node',ctx['node_id'],{'state':'updating'})
            writable(repository,ctx)
            ids=[save_record(repository,ctx,v,identifier('archive',ctx['node_id'],str(i)))['event_id'] for i,v in enumerate(entries)]
            adopted=manuscripts.adoption(repository,ctx['node_id'])
            reply=manuscripts.packet(repository,ctx['node_id'])
            if not reply:raise ContractError('PACKET_NOT_FOUND','Save a complete author reply before archival')
            object_ids=list(dict.fromkeys(repository.owner(i)['object_id'] for i in ids))
            content={'event_ids':ids,'author_packet_event_id':reply['event_id'],'object_ids':object_ids}
            if adopted:content['adoption_event_id']=adopted['event_id']
            append(repository,ctx,'director_archive',ctx['node_id'],content,identifier('archival',ctx['node_id']))
            if node['state']=='active':repository.update('node',ctx['node_id'],{'state':'active'})
            else:Operations(repository).publish(ctx['node_id'],ctx['branch_id'])
    from .lifecycle import status
    return status(repository,ctx['node_id'],output_root=params.get('output_root'))
