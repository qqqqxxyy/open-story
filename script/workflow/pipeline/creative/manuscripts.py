"""Immutable attempts and lightweight adoption; no literary judgement."""
import hashlib
import json
from script.util.errors import ContractError
from ..story import Operations
from .common import append, context, identifier, latest, local, messages


def attempt(repository, node_id):
    row=latest(repository,node_id,'scene_attempt')
    return row['content'] if row else None


def adoption(repository, node_id):
    return latest(repository,node_id,'scene_adoption')


def for_request(repository, branch_id, request_id):
    head=repository.branch(branch_id)['head']
    if not head:return None
    rows=repository.source_records(head['node_id'],event_types=['scene_attempt'])
    return next((r for r in rows if r['event']['content']['request_id']==request_id
                 and r['event']['content']['branch_id']==branch_id),None)


def input_hash(raw):
    return hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode('utf8')).hexdigest()


def start(repository, node_id, branch_id, request_id, kind, content, base=None, output_root=None):
    ctx=context(repository,node_id,branch_id)
    current=attempt(repository,node_id)
    old=for_request(repository,branch_id,request_id)
    raw=messages(content)
    if old:
        value=old['event']['content']
        if old['node_id']!=node_id or value['kind']!=kind or value['input_hash']!=input_hash(raw) or value.get('base_author_packet_event_id')!=base:
            raise ContractError('IDEMPOTENCY_CONFLICT','Request identity has different input or revision base')
        if current and current['attempt_id']!=value['attempt_id']:
            raise ContractError('STALE_MANUSCRIPT','This request belongs to an earlier attempt')
        return value
    node=repository.require('node',node_id)
    if node['state']=='active' or adoption(repository,node_id):
        raise ContractError('MANUSCRIPT_ACCEPTED','Accepted prose requires the historical rewrite workflow')
    Operations(repository)._leaf_branch(node_id,branch_id)
    if kind!='initial':
        packet=latest(repository,node_id,'author_packet')
        if not packet or packet['event_id']!=base or packet['content']['narrative_event_id']!=node['narrative_event_id']:
            raise ContractError('STALE_MANUSCRIPT','Revision must name the current complete author packet')
        display=latest(repository,node_id,'display_metadata')
        if not display_matches(repository,node_id,packet):
            raise ContractError('DISPLAY_REQUIRED','Display the current manuscript before reader revision')
        ensure_displayed(repository,node_id,branch_id,output_root)
    aid=identifier('attempt',node_id,request_id)
    with repository.transaction():
        inputs=list(ctx['raw_input_event_ids']) if kind=='initial' else [append(repository,ctx,'user_input',node_id,
            {'raw_user_messages':raw},identifier('input',node_id,aid))['event_id']]
        value={'attempt_id':aid,'request_id':request_id,'branch_id':branch_id,'kind':kind,
               'input_hash':input_hash(raw),'raw_input_event_ids':inputs,'base_author_packet_event_id':base}
        append(repository,ctx,'scene_attempt',node_id,value,aid)
    return value


def check_attempt(repository, node_id, supplied=None):
    value=attempt(repository,node_id)
    if supplied and (not value or value['attempt_id']!=supplied):
        raise ContractError('STALE_MANUSCRIPT','Use the current attempt ID')
    if adoption(repository,node_id):
        raise ContractError('MANUSCRIPT_ACCEPTED','Accepted prose cannot be revised in place')
    return value


def author_id(repository, node_id):
    value=attempt(repository,node_id)
    return identifier('author',node_id,value['attempt_id']) if value else identifier('author',node_id)


def packet(repository,node_id):
    value=attempt(repository,node_id)
    rows=local(repository,node_id,['author_packet'])
    return next((r['event'] for r in reversed(rows) if not value or
                 r['event']['content'].get('attempt_id')==value['attempt_id']),None)


def display_matches(repository,node_id,reply=None):
    reply=reply or packet(repository,node_id)
    display=latest(repository,node_id,'display_metadata')
    if not reply or not display:return False
    tag=display['content'].get('_manuscript')
    if attempt(repository,node_id):
        return bool(tag and tag['author_packet_event_id']==reply['event_id'] and
                    tag['narrative_event_id']==reply['content']['narrative_event_id'])
    return True


def ensure_displayed(repository,node_id,branch_id,output_root=None):
    from .lifecycle import status
    display=latest(repository,node_id,'display_metadata')
    tag=display['content'].get('_manuscript',{}) if display else {}
    state=status(repository,node_id,branch_id,output_root or tag.get('output_root'))
    if not state['display_snapshot_available'] or (tag.get('html_required') and not state['display_html_available']):
        raise ContractError('DISPLAY_REQUIRED','The current manuscript is not published to its configured reader')
    return state


def accept(repository,params):
    node_id=params['node_id'];branch_id=params['branch_id']
    Operations(repository)._scope(branch_id,node_id)
    request=params.get('request_id')
    if request:
        head=repository.branch(branch_id)['head']
        prior=next((row for row in repository.source_records(head['node_id'],event_types=['scene_adoption'])
            if row['event']['content'].get('request_id')==request and row['event']['content'].get('branch_id')==branch_id),None)
        if prior and (prior['node_id']!=node_id or prior['event']['content']['author_packet_event_id']!=params.get('author_packet_event_id')):
            raise ContractError('IDEMPOTENCY_CONFLICT','Adoption request belongs to a different manuscript')
    old=adoption(repository,node_id)
    expected=params.get('author_packet_event_id')
    if old:
        if expected and old['content']['author_packet_event_id']!=expected:
            raise ContractError('STALE_MANUSCRIPT','Another manuscript was adopted')
        return old
    node=repository.require('node',node_id)
    if node['state']=='active':return None  # Completed legacy history needs no invented adoption.
    reply=packet(repository,node_id)
    if not reply or (expected and reply['event_id']!=expected):
        raise ContractError('STALE_MANUSCRIPT','Name the complete current author packet')
    if not display_matches(repository,node_id,reply):
        raise ContractError('DISPLAY_REQUIRED','Adoption requires matching display metadata')
    ensure_displayed(repository,node_id,branch_id,params.get('output_root'))
    display=latest(repository,node_id,'display_metadata')
    with repository.transaction():
        ctx=context(repository,node_id,branch_id)
        value={'author_packet_event_id':reply['event_id'],'narrative_event_id':reply['content']['narrative_event_id'],
               'display_event_id':display['event_id'],'director_packet_event_id':reply['content']['director_packet_event_id'],
               'attempt_id':reply['content'].get('attempt_id'),'request_id':request,'branch_id':branch_id}
        result=append(repository,ctx,'scene_adoption',node_id,value,identifier('adoption',node_id))
        Operations(repository).publish(node_id,branch_id)
    return result
