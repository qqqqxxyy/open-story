"""Durable, scoped maintenance after a newer manuscript has been displayed."""
from copy import deepcopy
from script.util.errors import ContractError
from .common import append, context, identifier, latest, maintenance_scope, settings
from . import manuscripts


def _write(repository,ctx,kind,content,event_id):
    with repository.transaction(),maintenance_scope(ctx):
        node=repository.require('node',ctx['node_id'])
        if node['state']=='active':repository.update('node',ctx['node_id'],{'state':'updating'})
        result=append(repository,ctx,kind,ctx['node_id'],content,event_id)
        if node['state']=='active':repository.update('node',ctx['node_id'],{'state':'active'})
        return result


def _trigger(repository,branch,packet_id):
    packet=repository.require('event',packet_id);head=repository.branch(branch)['head']
    if packet['event_type']!='author_packet' or not head or repository.owner(packet_id)['node_id']!=head['node_id']:
        raise ContractError('MAINTENANCE_SCOPE','Trigger must be the displayed branch head packet')
    if packet['content']['narrative_event_id']!=head['narrative_event_id'] or not manuscripts.display_matches(repository,head['node_id'],packet):
        raise ContractError('DISPLAY_REQUIRED','Display the current head before ancestor maintenance')
    manuscripts.ensure_displayed(repository,head['node_id'],branch)
    return head


def inspect(repository,branch,trigger):
    head=_trigger(repository,branch,trigger)
    path=repository.ancestor_path(head['node_id'])
    # One metadata query for the whole ancestor path, not a query per scene.
    metadata={}
    for row in repository.source_records(head['node_id'],event_types=[
            'scene_adoption','scene_maintenance','scene_maintenance_complete','director_archive']):
        metadata.setdefault(row['node_id'],{})[row['event']['event_type']]=row['event']
    for node_id in path:
        state=metadata.get(node_id,{})
        adopted=state.get('scene_adoption')
        if not adopted or state.get('scene_maintenance_complete'):continue
        saved=state.get('scene_maintenance')
        if saved is None:
            ctx=dict(context(repository,node_id));ctx['history_event_seq']=repository.max_sequence('event')
            ctx['branch_id']=branch
            ctx['maintenance_job_id']=identifier('maintenance',adopted['event_id'])
            saved=_write(repository,ctx,'scene_maintenance',{'scope':ctx,'adoption_event_id':adopted['event_id']},
                         identifier('maintenance',adopted['event_id']))
        ctx=deepcopy(saved['content']['scope']);ctx['branch_id']=branch
        job={'job_id':saved['event_id'],'node_id':node_id,'adoption_event_id':adopted['event_id'],
             'adopted':adopted['content'],'scope':ctx,'phase':'semantic_pending'}
        archive=state.get('director_archive')
        if archive:
            if settings()['capsule_mode']:
                from .capsule.service import check
                ids=archive['content'].get('object_ids',[])
                with maintenance_scope(ctx):jobs=check(repository,{'node_id':node_id,'branch_id':branch,'object_ids':ids})
                if jobs['objects']:
                    job.update(phase='capsule_pending',capsule_jobs=jobs)
                    return {'next_job':job,'complete':False}
            _write(repository,ctx,'scene_maintenance_complete',{'adoption_event_id':adopted['event_id'],
                'archive_event_id':archive['event_id']},identifier('maintenance-complete',adopted['event_id']))
            continue
        return {'next_job':job,'complete':False}
    return {'next_job':None,'complete':True}


def execute(repository,params):
    from .scenes import _outside_transaction
    _outside_transaction(repository)
    branch=params['branch_id'];trigger=params['trigger_author_packet_event_id']
    current=inspect(repository,branch,trigger);content=params.get('content')
    if content is None:return current
    job_id=params.get('job_id')
    if not job_id:raise ContractError('MAINTENANCE_SCOPE','Submit content with its returned job ID')
    stored=repository.require('event',job_id)
    if stored['event_type']!='scene_maintenance':raise ContractError('MAINTENANCE_SCOPE','Use a maintenance job')
    node_id=repository.owner(job_id)['node_id'];ctx=deepcopy(stored['content']['scope']);ctx['branch_id']=branch
    from ..story import Operations
    Operations(repository)._scope(branch,node_id)
    adopted=manuscripts.adoption(repository,node_id)
    if not adopted or adopted['event_id']!=stored['content']['adoption_event_id']:
        raise ContractError('MAINTENANCE_SCOPE','Maintenance adoption does not match')
    if repository.require('node',node_id)['narrative_event_id']!=adopted['content']['narrative_event_id']:
        raise ContractError('STALE_MANUSCRIPT','Adopted prose changed')
    # A completed job may be replayed, but never replace its saved semantic content.
    if current['next_job'] and current['next_job']['job_id']!=job_id and not latest(repository,node_id,'scene_maintenance_complete'):
        raise ContractError('MAINTENANCE_SCOPE','Process the oldest returned job first')
    with maintenance_scope(ctx):
        if 'events' in content:
            from .business import archive
            archive(repository,{'node_id':node_id,'branch_id':branch,'content':{
                'events':content['events'],'default_source_event_ids':[adopted['content']['narrative_event_id']]}})
        elif 'capsules' in content:
            if not latest(repository,node_id,'director_archive'):
                raise ContractError('MAINTENANCE_SCOPE','Save semantic records before capsules')
            requested=current.get('next_job')
            allowed=[]
            if requested and requested['job_id']==job_id and requested['phase']=='capsule_pending':
                for obj in requested['capsule_jobs']['objects']:
                    for level in (1,2):
                        allowed.extend((obj['object_id'],level,batch['source_event_ids'],batch['supersedes_capsule_event_ids'])
                            for batch in obj['level_'+str(level)]['batches'])
            from .common import scoped_sources
            existing=[row for row in scoped_sources(repository).local(node_id) if row['event']['event_action']=='summarize']
            for entry in content['capsules']:
                signature=(entry['object_id'],entry['level'],entry['source_event_ids'],entry.get('supersedes_capsule_event_ids',[]))
                body={**entry['content'],'_capsule':{'level':entry['level'],'source_event_ids':entry['source_event_ids'],
                    'supersedes_capsule_event_ids':entry.get('supersedes_capsule_event_ids',[])}}
                if ctx.get('maintenance_job_id'):body['_capsule']['maintenance_job_id']=ctx['maintenance_job_id']
                replay=any(row['object_id']==entry['object_id'] and row['event']['content']==body for row in existing)
                if signature not in allowed and not replay:
                    raise ContractError('MAINTENANCE_SCOPE','Submit only returned capsule batches or their exact retries')
            from .capsule.service import save
            save(repository,{'node_id':node_id,'branch_id':branch,'content':{'capsules':content['capsules']}})
        else:raise ContractError('MAINTENANCE_SCOPE','Submit the requested events or capsules batch')
    return inspect(repository,branch,trigger)


def read_context(repository,params):
    """Explicit recovery lookup using a job's scope; never normal draft recall."""
    stored=repository.require('event',params['maintenance_job_id'])
    if stored['event_type']!='scene_maintenance' or repository.owner(stored['event_id'])['node_id']!=params['node_id']:
        raise ContractError('MAINTENANCE_SCOPE','Read the target node of this maintenance job')
    ctx=deepcopy(stored['content']['scope']);ctx['branch_id']=params.get('branch_id') or ctx['branch_id']
    from ..story import Operations
    Operations(repository)._scope(ctx['branch_id'],ctx['node_id'])
    adopted=manuscripts.adoption(repository,ctx['node_id'])
    if not adopted or adopted['event_id']!=stored['content']['adoption_event_id'] or \
            repository.require('node',ctx['node_id'])['narrative_event_id']!=adopted['content']['narrative_event_id']:
        raise ContractError('STALE_MANUSCRIPT','The maintenance manuscript no longer matches')
    from .recall import lookup
    with maintenance_scope(ctx):return lookup(repository,{k:v for k,v in params.items() if k!='maintenance_job_id'})
