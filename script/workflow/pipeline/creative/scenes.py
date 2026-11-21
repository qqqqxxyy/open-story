"""Persisted scene composition. Reader publication precedes ancestor maintenance."""
from script.util.errors import ContractError
from . import lifecycle, recall, handoff, presentation, manuscripts
from .common import context, latest, settings


def _outside_transaction(repository):
    if repository.in_transaction:
        raise ContractError('COMPOSITE_IN_BATCH','Run persisted scene stages outside a batch transaction')


def prepare(repository,params):
    _outside_transaction(repository)
    action=params.get('action');branch=params.get('branch_id','main');active=None;adopted=None
    opening={k:params[k] for k in ('node_id','branch_id','mode','content') if k in params}
    if not action:
        scene=lifecycle.open_scene(repository,opening)
    elif action=='resume':
        node=params.get('node_id') or repository.branch(branch)['head']['node_id']
        scene=lifecycle.status(repository,node,branch,params.get('output_root'))
        active=manuscripts.attempt(repository,node)
        if not active and params.get('request_id') and repository.require('node',node)['state']=='creating' and not manuscripts.packet(repository,node):
            from script.workflow.data.creative import CreativeRepository
            from .common import messages
            ctx=context(repository,node,branch)
            raw=[m for row in CreativeRepository(repository).referenced(ctx,ctx['raw_input_event_ids']) for m in messages(row['event']['content'])]
            active=manuscripts.start(repository,node,branch,params['request_id'],'initial',{'raw_user_messages':raw})
            scene=lifecycle.status(repository,node,branch,params.get('output_root'))
    else:
        previous=manuscripts.for_request(repository,branch,params['request_id'])
        if previous:
            value=previous['event']['content']
            from .common import messages
            kind='initial' if action=='next' else params['revision_kind']
            if params.get('node_id',previous['node_id'])!=previous['node_id']:
                raise ContractError('IDEMPOTENCY_CONFLICT','Request identity belongs to a different scene')
            if action=='next' and context(repository,previous['node_id'],branch)['mode']!=params.get('mode','normal'):
                raise ContractError('IDEMPOTENCY_CONFLICT','Request identity has a different scene mode')
            if value['input_hash']!=manuscripts.input_hash(messages(params['content'])) or value['kind']!=kind or (
                action=='revise' and value['base_author_packet_event_id']!=params['base_author_packet_event_id']):
                raise ContractError('IDEMPOTENCY_CONFLICT','Request identity has different input')
            node=previous['node_id'];active=manuscripts.attempt(repository,node)
            if active['attempt_id']!=value['attempt_id']:
                raise ContractError('STALE_MANUSCRIPT','Request belongs to a superseded attempt')
        elif action=='revise':
            node=params['node_id']
            active=manuscripts.start(repository,node,branch,params['request_id'],params['revision_kind'],
                                     params['content'],params['base_author_packet_event_id'],params.get('output_root'))
        else:
            with repository.transaction():
                head=repository.branch(branch)['head']
                if head and head['state']=='creating' and latest(repository,head['node_id'],'scene_context'):
                    if not params.get('expected_author_packet_event_id'):
                        raise ContractError('STALE_MANUSCRIPT','Name the displayed predecessor packet before continuing')
                    adopted=manuscripts.accept(repository,{'node_id':head['node_id'],'branch_id':branch,
                        'author_packet_event_id':params['expected_author_packet_event_id'],'output_root':params.get('output_root'),'request_id':params['request_id']})
                scene=lifecycle.open_scene(repository,opening)
                node=scene['node_id']
                active=manuscripts.start(repository,node,branch,params['request_id'],'initial',params['content'])
        scene=lifecycle.status(repository,node,branch,params.get('output_root'))
    result={'scene':scene,'preparation':None,'next_operation':None,'next_action':'wait_for_reader',
            'attempt':active,'accepted_predecessor':adopted}
    if scene['status'] in ('awaiting_display','awaiting_archive','awaiting_feedback','complete',
                            'accepted_pending_archive','accepted_pending_capsules','cancelled'):
        if scene['status']=='awaiting_display':result.update(next_operation='scene.submit',next_action='restore_display')
        elif action=='resume' and scene['status']!='cancelled':
            head=repository.branch(branch)['head'];reply=manuscripts.packet(repository,head['node_id']) if head else None
            if reply and manuscripts.display_matches(repository,head['node_id'],reply):
                state=lifecycle.status(repository,head['node_id'],branch)
                tag=latest(repository,head['node_id'],'display_metadata')['content'].get('_manuscript',{})
                if state['display_snapshot_available'] and (not tag.get('html_required') or state['display_html_available']):
                    from .maintenance import inspect
                    result['maintenance']=inspect(repository,branch,reply['event_id'])
                    result['maintenance_trigger_author_packet_event_id']=reply['event_id']
                    if result['maintenance']['next_job']:
                        result.update(next_operation='scene.maintenance',next_action='restore_maintenance')
                    if scene['published']:result['scene']=lifecycle.status(repository,scene['node_id'],branch)
            if scene['status'] in ('accepted_pending_archive','accepted_pending_capsules') and 'maintenance' not in result:
                result.update(next_operation='scene.status',next_action='resume_branch_head',resume_node_id=head['node_id'])
        return result
    if active and active['kind']=='minor':
        result.update(next_action='revise_prose',next_operation='scene.submit');return result
    if action=='resume' and scene['director_handoff_event_id']:
        director=repository.require('event',scene['director_handoff_event_id'])
        if not active or director['content'].get('attempt_id')==active['attempt_id']:
            if scene['mode']=='dialogue':result.update(next_operation='dialogue.read',next_action='resume_dialogue')
            else:result.update(next_operation='scene.submit',next_action='write_prose')
            return result
    controls={k:params[k] for k in ('branch_id','scene_need','character_ids','event_ids','object_ids','view') if k in params}
    try:result['preparation']=recall.recall(repository,{**controls,'node_id':scene['node_id']})
    except Exception as exc:
        raise ContractError(getattr(exc,'code','OPERATION_FAILED'),str(exc),details={
            'node_id':scene['node_id'],'completed_stage':'scene_opened','resume_operation':'scene.context'}) from exc
    result.update(next_operation='director.save',next_action='design_scene')
    return result


def submit(repository,params):
    _outside_transaction(repository)
    ctx=context(repository,params['node_id'],params.get('branch_id'))
    active=manuscripts.check_attempt(repository,ctx['node_id'],params.get('attempt_id'))
    existing=params.get('author_packet_event_id')
    if existing:
        packet=repository.require('event',existing);node=repository.require('node',ctx['node_id'])
        if packet['event_type']!='author_packet' or repository.owner(existing)['node_id']!=ctx['node_id'] or packet['content']['narrative_event_id']!=node['narrative_event_id']:
            raise ContractError('PACKET_NOT_FOUND','Use this scene current complete author packet')
        if active and packet['content'].get('attempt_id')!=active['attempt_id']:
            raise ContractError('STALE_MANUSCRIPT','Use the current attempt packet')
        reply={'packet_event_id':existing,'narrative_event_id':packet['content']['narrative_event_id']}
    else:
        reply=handoff.save_author(repository,{'node_id':ctx['node_id'],'branch_id':ctx['branch_id'],
            'source_packet_event_id':params['source_packet_event_id'],**({'attempt_id':active['attempt_id']} if active else {}),
            'content':{k:v for k,v in params['content'].items() if k!='display'}})
    controls={k:params[k] for k in ('output_root','generate') if k in params}
    try:display=presentation.display(repository,{'node_id':ctx['node_id'],'branch_id':ctx['branch_id'],
            'content':params['content']['display'],**controls})
    except Exception as exc:
        metadata=latest(repository,ctx['node_id'],'display_metadata')
        details={'node_id':ctx['node_id'],'author_packet_event_id':reply['packet_event_id'],
            'narrative_event_id':reply['narrative_event_id'],'completed_stage':'author_saved','resume_operation':'scene.submit'}
        if metadata:details['display_event_id']=metadata['event_id']
        raise ContractError(getattr(exc,'code','OPERATION_FAILED'),str(exc),details=details) from exc
    state=lifecycle.status(repository,ctx['node_id'],output_root=params.get('output_root'))
    result={'node_id':ctx['node_id'],'author_packet_event_id':reply['packet_event_id'],
        'narrative_event_id':reply['narrative_event_id'],'display_event_id':state['display_event_id'],
        'status':state['status'],'display':display,'next_operation':'scene.status' if state['published'] else (
            'capsule.check' if settings()['capsule_mode'] else 'scene.archive')}
    if active and state['status']=='awaiting_display':
        result.update(next_operation='scene.submit',next_action='restore_display')
        return result
    if active:
        from .maintenance import inspect
        try:result['maintenance']=inspect(repository,ctx['branch_id'],reply['packet_event_id'])
        except Exception as exc:
            raise ContractError(getattr(exc,'code','OPERATION_FAILED'),str(exc),details={
                'node_id':ctx['node_id'],'attempt_id':active['attempt_id'],
                'author_packet_event_id':reply['packet_event_id'],'narrative_event_id':reply['narrative_event_id'],
                'display_event_id':state['display_event_id'],'completed_stage':'display_published',
                'resume_operation':'scene.maintenance'}) from exc
        result['next_operation']='scene.maintenance' if result['maintenance']['next_job'] else None
        result['next_action']='maintain_ancestors' if result['maintenance']['next_job'] else 'wait_for_reader'
    return result


def accept(repository,params):
    _outside_transaction(repository)
    adopted=manuscripts.accept(repository,params)
    from .maintenance import inspect
    state=lifecycle.status(repository,params['node_id'],params['branch_id'],params.get('output_root'))
    try:pending=inspect(repository,params['branch_id'],params['author_packet_event_id'])
    except Exception as exc:
        raise ContractError(getattr(exc,'code','OPERATION_FAILED'),str(exc),details={
            'node_id':params['node_id'],'author_packet_event_id':params['author_packet_event_id'],
            'completed_stage':'manuscript_accepted','resume_operation':'scene.maintenance'}) from exc
    state=lifecycle.status(repository,params['node_id'],params['branch_id'],params.get('output_root'))
    return {'node_id':params['node_id'],'adoption_event_id':adopted['event_id'] if adopted else None,
            'status':state['status'],'maintenance':pending}
