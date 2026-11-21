"""Range-confirmed deletion and atomic restart from a surviving parent."""
from hashlib import sha256
import json
from script.util.errors import ContractError
from .creative.common import messages


def plan(repository, params, rewrite=False):
    anchor=repository.require('node',params['node_id'])
    include=True if rewrite else params['include_target']
    if include and anchor['node_type']=='root':raise ContractError('ROOT_PROTECTED','Root is not a scene')
    rows=[{**item['node'],'depth':item['depth']} for item in repository.descendants(anchor['node_id'],include)]
    ids=[row['node_id'] for row in rows]
    context=repository.range_deletion_context(ids)
    if context['external_references']:raise ContractError('EXTERNAL_DEPENDENCY','Surviving references prevent range deletion')
    branch_ids=context['branch_ids']
    selected=params.get('branch_id') or ('main' if 'main' in branch_ids else branch_ids[0] if branch_ids else None)
    if selected and branch_ids and selected not in branch_ids:
        raise ContractError('CROSS_BRANCH_REFERENCE','Selected branch is outside deletion range')
    parent=anchor['predecessor_node_id'] if include else anchor['node_id']
    proposal={'node_id':anchor['node_id'],'include_target':include,'deleted_node_ids':ids,'node_count':len(ids),
              'affected_branches':branch_ids,'resume_node_id':parent,'branch_id':selected,'rewrite':rewrite}
    # Include records, dependencies and heads in the receipt; any changed scope needs new confirmation.
    fingerprint={**proposal,'records':rows,'context':context,
                 'request_content':params.get('content')}
    proposal['confirmation_token']=sha256(json.dumps(fingerprint,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return proposal,context


def execute(repository, params, rewrite=False):
    target=repository.get('node',params['node_id'])
    new_id='node-rewrite-'+sha256(params['node_id'].encode()).hexdigest()[:24]
    if rewrite and target is None and repository.get('node',new_id):
        from .creative.lifecycle import status
        from .creative.common import context
        old=context(repository,new_id,params.get('branch_id'))
        if old.get('rewrite_origin',{}).get('request')!=params['content']:
            raise ContractError('IDEMPOTENCY_CONFLICT','Rewrite retry must preserve the original request')
        return {'status':'rewritten','already_done':True,'scene':status(repository,new_id), 'display':None}
    with repository.transaction():
        proposal,context=plan(repository,params,rewrite)
        count=proposal['node_count']
        if count>1 and (not params.get('user_confirmed') or params.get('confirmation_token')!=proposal['confirmation_token']):
            return {'status':'confirmation_required','proposal':proposal,'scene':None,'display':None}
        original=[]
        if rewrite:
            for row in repository.source_records(None,current_node_id=target['node_id'],event_types=['user_input']):
                if row['event']['event_action'] != 'summarize':
                    original.extend(messages(row['event']['content']))
        repository.remove_range(context,proposal['deleted_node_ids'])
        parent=proposal['resume_node_id'];branch=proposal['branch_id']
        if parent and branch and not repository.has_successors(parent):repository.assign_head(branch,parent)
        scene=None
        if rewrite:
            from .creative.lifecycle import open_scene
            incoming=messages(params['content'])
            scene=open_scene(repository,{'node_id':new_id,'branch_id':branch,'mode':'normal',
                'content':{'raw_user_messages':original+incoming}},origin={'replaces_node_id':params['node_id'],
                'request':params['content']})
    from .creative.presentation import sync
    display_error=None
    try:display=sync(repository,params)
    except ContractError as exc:
        if exc.code!='DISPLAY_FAILED':raise
        display=None;display_error={'code':exc.code,'message':str(exc)}
    return {'status':'rewritten' if rewrite else 'deleted','proposal':proposal,'scene':scene,'display':display,'display_error':display_error}
