"""Creative scope, immutable records and configuration access."""
from hashlib import sha256
from contextvars import ContextVar
from contextlib import contextmanager

_MAINTENANCE=ContextVar("openstory_maintenance",default=None)

@contextmanager
def maintenance_scope(ctx):
    token=_MAINTENANCE.set(ctx)
    try:yield ctx
    finally:_MAINTENANCE.reset(token)

def in_maintenance(ctx):return _MAINTENANCE.get() is ctx


from copy import deepcopy
from script.util.runtime import current, AGENT
from script.util.contracts import validate
from script.util.errors import ContractError
from script.workflow.data.creative import CreativeRepository
from ..story import Operations


class _MaintenanceSources(CreativeRepository):
    def sources(self,*args,**kwargs):
        rows=super().sources(*args,**kwargs)
        ctx=_MAINTENANCE.get()
        if ctx and ctx.get('maintenance_job_id'):
            from .visibility import maintenance_rows
            return maintenance_rows(self.repository,ctx,rows)
        return rows


def scoped_sources(repository):
    return _MaintenanceSources(repository) if _MAINTENANCE.get() else CreativeRepository(repository)


def settings():
    return current().settings['creative']


def enabled():
    # Capsule mode augments recall; ordinary creative operations remain available.
    return True


def identifier(prefix, *parts):
    return prefix+'-'+sha256('\0'.join(parts).encode('utf8')).hexdigest()[:32]


def context(repository, node_id, branch_id=None):
    override=_MAINTENANCE.get()
    if override and override['node_id']==node_id and (branch_id is None or override['branch_id']==branch_id):return override
    node = repository.require('node', node_id)
    event = repository.get('event', identifier('scene', node_id))
    if event is None:
        raise ContractError('SCENE_CONTEXT_MISSING', 'This node was not opened by scene-next')
    result = {**event['content'], 'node_id': node_id}
    current_attempt=latest(repository,node_id,'scene_attempt')
    if current_attempt:
        value=current_attempt['content']
        result['attempt_id']=value['attempt_id']
        result['raw_input_event_ids']=list(dict.fromkeys(result['raw_input_event_ids']+value['raw_input_event_ids']))
    if branch_id and result['branch_id'] != branch_id:
        raise ContractError('CROSS_BRANCH_REFERENCE', 'Scene belongs to another branch')
    Operations(repository)._scope(result['branch_id'], node_id)
    return result


def writable(repository, ctx):
    if not in_maintenance(ctx):Operations(repository)._leaf_branch(ctx['node_id'], ctx['branch_id'])
    else:Operations(repository)._scope(ctx['branch_id'],ctx['node_id'])
    Operations(repository)._writing(ctx['node_id'])


def business_context(repository, node_id, branch_id=None):
    if repository.get('event',identifier('scene',node_id)):
        return context(repository,node_id,branch_id)
    node=repository.require('node',node_id)
    if branch_id is None:
        branch=repository.head_owner(node_id)
        if branch is None:
            raise ContractError('BRANCH_REQUIRED','Maintenance of a shared historical node requires branch-id')
        branch_id=branch['branch']['object_id']
    Operations(repository)._scope(branch_id,node_id)
    return {'node_id':node_id,'branch_id':branch_id,'mode':'normal','history_node_id':node_id,
            'history_event_seq':repository.max_sequence('event'),'raw_input_event_ids':[],
            'previous_narrative_event_id':node['narrative_event_id'],'previous_summary_event_id':node['summary_event_id']}


def workflow_object(kind, key, name=None):
    definition = settings()['workflow_objects'].get(kind)
    object_key = definition['key'] if definition else key
    return {'object_id': kind+'_'+object_key, 'object_type': kind, 'object_key': object_key,
            'name': definition['name'] if definition else name or key}


def append(repository, ctx, kind, key, content, event_id=None, name=None, select_as=None, event_action='append'):
    from uuid import uuid4
    obj = workflow_object(kind, key, name)
    # Existing immutable receipts retain their original ownership when replayed.
    if event_id and kind in settings()['workflow_objects'] and repository.get('event', event_id):
        obj = repository.require('object', repository.owner(event_id)['object_id'])
    result = Operations(repository).create_event({'node_id': ctx['node_id'], 'branch_id': ctx['branch_id'],
        'object': obj,
        'event': {'event_id': event_id or 'event-'+uuid4().hex, 'event_type': kind,
                  'type_name': key, 'event_action': event_action, 'content': deepcopy(content)},
        **({'select_as': select_as} if select_as else {})})
    return result['event']


def local(repository, node_id, kinds=None):
    rows = CreativeRepository(repository).local(node_id, kinds)
    return [row for row in rows if row['node_id'] == node_id and row['event']['event_action'] != 'summarize']


def latest(repository, node_id, kind):
    rows = local(repository, node_id, [kind])
    return rows[-1]['event'] if rows else None


def validate_content(kind, content):
    category = settings()['categories'].get(kind)
    if category and category.get('schema'):
        current().validator.validate(content, category['schema'])


def get_path(value, path, default=None):
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def messages(content):
    from .actions import unpack
    content,_=unpack(content)
    values = content.get('raw_user_messages')
    if values is None:
        return [{'text': content.get('raw_player_input', content.get('text', '')),
                 'source': content.get('source', 'assistant_transcribed')}]
    default = AGENT['definitions']['raw_input_message']['properties']['source']['default']
    return [{**deepcopy(message), 'source': message.get('source', default)} for message in values]
