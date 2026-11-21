"""Story and branch metadata; lifecycle does not change head ownership."""
from uuid import uuid4
from script.util.errors import ContractError


def root_node(repository):
    nodes=repository.records('node', {'node_type':'root'}, limit=1)
    if not nodes: raise ContractError('ROOT_MISSING','Initialize a story before management')
    return nodes[0]


def lifecycle(repository, object_id, kind, default):
    rows=repository.source_records(root_node(repository)['node_id'],object_ids=[object_id],event_types=[kind])
    if rows:return rows[-1]['event']['content']['lifecycle']
    return default


def story_state(repository):
    return lifecycle(repository,'story','story_lifecycle','active')


def branch_state(repository, branch_id):
    return lifecycle(repository,branch_id,'branch_lifecycle','open')


def permit_write(repository, branch_id):
    if story_state(repository)=='archived': raise ContractError('STORY_ARCHIVED','Restore the story before creation')
    if branch_state(repository,branch_id)!='open': raise ContractError('BRANCH_CLOSED','Reopen the branch before creation')


def set_state(repository, params, kind):
    root=root_node(repository); is_story=kind=='story_lifecycle'
    object_id='story' if is_story else params['branch_id']
    if is_story:
        repository.ensure_object({'object_id':'story','object_type':'story','object_key':repository.identity()['database_id'],'name':'story'})
    else: repository.branch(object_id)
    default='active' if is_story else 'open'
    previous=lifecycle(repository,object_id,kind,default)
    if previous!=params['lifecycle']:
        with repository.transaction():
            repository.update('node',root['node_id'],{'state':'updating'})
            repository.append_event(root['node_id'],object_id,{'event_id':'management-'+uuid4().hex,
                'event_type':kind,'type_name':'lifecycle','content':{'lifecycle':params['lifecycle'],'reason':params.get('reason','')}})
            repository.update('node',root['node_id'],{'state':'active'})
    return {'lifecycle':params['lifecycle'],'already_set':previous==params['lifecycle'],
            **({'branch_id':object_id} if not is_story else {})}


def branches(repository):
    return [{**repository.branch(obj['object_id']),'lifecycle':branch_state(repository,obj['object_id'])}
            for obj in repository.records('object',{'object_type':'branch'})]


def info(repository):
    root=root_node(repository)
    identity=repository.get('object','story')
    inputs=repository.source_records(root['node_id'],event_types=['story_identity','story_setting'])
    from .creative.actions import unpack
    title=identity['name'] if identity else repository.identity()['database_id']
    story_id=repository.identity()['database_id']
    for row in inputs:
        event=row['event']; content,_=unpack(event['content'])
        if event['event_type']=='story_identity':
            story_id=content['story_id'];title=content['title']
        elif event['type_name']=='title' and isinstance(content,str):title=content
    return {'story_id':story_id,'title':title,'root_node_id':root['node_id'],'lifecycle':story_state(repository),
            'counts':repository.info()['counts'],'branches':branches(repository)}


def list_stories(data_root, environment=None):
    from script.workflow.data.catalog import descriptors,open_metadata
    result=[]
    for descriptor in descriptors(data_root,environment):
        with open_metadata(descriptor['config_path']) as repository:
            result.append({**descriptor,**info(repository)})
    return result
