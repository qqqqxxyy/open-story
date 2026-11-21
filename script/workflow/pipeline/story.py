"""Branch lifecycle, visibility and story operations. Persistence uses repository port."""
from uuid import uuid4
from script.util.contracts import ContractError as DataError
from script.workflow.data.interface import StoryRepository

class Operations:
    def __init__(self,repository:StoryRepository):self.repository=repository
    def _scope(self,branch_id,at_node_id=None):
        view=self.repository.branch(branch_id)
        if view['head'] is None:raise DataError('BRANCH_INACTIVE','Branch has no head')
        head=view['head']['node_id'];end=at_node_id or head
        if end!=head and not self.repository.is_ancestor(head,end):raise DataError('CROSS_BRANCH_REFERENCE','Cutoff is outside the branch path')
        return {'branch_id':branch_id,'head_node_id':head,'at_node_id':end}
    def _leaf_branch(self,node_id,branch_id=None):
        if self.repository.has_successors(node_id):raise DataError('NOT_LEAF','Node has successors')
        view=self.repository.head_owner(node_id)
        if view is None:raise DataError('HEAD_REQUIRED','Leaf has no branch head')
        if branch_id and view['branch']['object_id']!=branch_id:raise DataError('CROSS_BRANCH_REFERENCE','Node is another branch head')
        return view
    def begin(self,p):
        r=self.repository;node_id=p['node_id'];branch_id=p['branch_id'];node_type=p.get('node_type','scene')
        with r.transaction():
            old=r.get('node',node_id)
            if old:
                self._leaf_branch(node_id,branch_id)
                if old['node_type']!=node_type or (p.get('predecessor_id') and old['predecessor_node_id']!=p['predecessor_id']):
                    raise DataError('IDENTITY_CONFLICT','Node identity differs')
                return old
            if node_type=='root':
                if r.query('node',{'node_type':'root'},limit=1)['items']:raise DataError('ROOT_EXISTS','Story already has a root')
                if p.get('predecessor_id'):raise DataError('INVALID_ROOT','Root has no predecessor')
                r.ensure_object({'object_id':branch_id,'object_type':'branch','object_key':branch_id,'name':branch_id})
                node=r.create('node',{'node_id':node_id,'node_type':'root'})
            else:
                from .management import permit_write
                permit_write(r,branch_id)
                scope=self._scope(branch_id);parent=p.get('predecessor_id',scope['head_node_id'])
                if parent!=scope['head_node_id']:raise DataError('STALE_HEAD','Continue only at the branch head; use branch.fork')
                if r.require('node',parent)['state']!='active':raise DataError('PREDECESSOR_INACTIVE','Publish the head before continuing')
                node=r.create('node',{'node_id':node_id,'predecessor_node_id':parent})
            r.assign_head(branch_id,node_id)
            return node
    def fork(self,p):
        r=self.repository
        from .management import story_state
        if story_state(r)=='archived':raise DataError('STORY_ARCHIVED','Restore before creating a branch')
        with r.transaction():
            anchor=r.require('node',p['from_node_id'])
            if anchor['state']!='active':raise DataError('PREDECESSOR_INACTIVE','Fork from an active node')
            if not r.has_successors(anchor['node_id']):raise DataError('FORK_AT_LEAF','Leaf continuation keeps its branch identity')
            old=r.get('object',p['branch_id'])
            if old and r.branch(p['branch_id'])['head']:raise DataError('BRANCH_EXISTS','Branch already has a head')
            branch=r.ensure_object({'object_id':p['branch_id'],'object_type':'branch','object_key':p['branch_id'],'name':p.get('name',p['branch_id'])})
            if p.get('name') and branch['name']!=p['name']:r.update('object',p['branch_id'],{'name':p['name']})
            node=r.create('node',{'node_id':p['node_id'],'predecessor_node_id':anchor['node_id']})
            r.assign_head(p['branch_id'],node['node_id'])
            return r.branch(p['branch_id'])
    def _writing(self,node_id):
        node=self.repository.require('node',node_id)
        if node['state'] not in ('creating','updating'):raise DataError('NODE_NOT_WRITABLE','Node is not writable')
        return node
    def create_event(self,p):
        r=self.repository
        with r.transaction():
            event=dict(p['event']);event.setdefault('event_id','event-'+uuid4().hex);event.setdefault('event_action','append')
            from .creative.actions import supported, validate_event, register_targets
            supported(event['event_action'])
            node=r.get('node',p['node_id'])
            if node is None:self.begin(p)
            self._scope(p['branch_id'],p['node_id'])
            old=r.get('event',event['event_id'])
            if old:
                owner=r.owner(event['event_id'])
                if (owner['node_id'],owner['object_id'])!=(p['node_id'],p['object']['object_id']) or any(old.get(k)!=v for k,v in event.items()):
                    raise DataError('IDEMPOTENCY_CONFLICT','Event identity/content differs')
                return {'event':old,'ownership':owner['relation'],'already_exists':True}
            from .management import permit_write
            permit_write(r,p['branch_id'])
            self._writing(p['node_id'])
            targets=validate_event(r,p['node_id'],p['object']['object_id'],event,p['branch_id'])
            if p.get('select_as') and event['event_action']!='append':raise DataError('INVALID_SELECTION','Narrative/summary pointers select append content only')
            r.ensure_object(p['object']);result=r.append_event(p['node_id'],p['object']['object_id'],event)
            register_targets(r,result['event']['event_id'],targets)
            if p.get('select_as'):
                key='literary_text' if p['select_as']=='narrative' else 'summary'
                valid=isinstance(event['content'],dict) and (isinstance(event['content'].get(key),str) or (p['select_as']=='narrative' and bool(event['content'].get('fragment_event_ids'))))
                if result['event']['state']!='active' or not valid:
                    raise DataError('INVALID_SELECTION','Select active content containing '+key)
                r.select(p['node_id'],result['event']['event_id'],p['select_as'])
            return result
    def publish(self,node_id,branch_id=None):
        r=self.repository
        with r.transaction():
            self._leaf_branch(node_id,branch_id);node=r.require('node',node_id)
            if node['state']=='active':return node
            self._writing(node_id)
            if node['node_type']=='scene':
                if not all(node[k] for k in ('predecessor_node_id','narrative_event_id','summary_event_id')):raise DataError('PUBLICATION_INCOMPLETE','Scene needs all three pointers')
                if r.require('node',node['predecessor_node_id'])['state']!='active':raise DataError('PREDECESSOR_INACTIVE','Predecessor is not active')
                selections=r.selection_records(node)
                for selection,key in (('narrative','literary_text'),('summary','summary')):
                    event=selections[node[selection+'_event_id']]
                    valid=isinstance(event['content'],dict) and (isinstance(event['content'].get(key),str) or (selection=='narrative' and bool(event['content'].get('fragment_event_ids'))))
                    if selection=='narrative' and valid:
                        from .creative.narrative import read
                        valid=bool(read(r,node))
                    if event['state']!='active' or r.owner(event['event_id'])['node_id']!=node_id or not valid:
                        raise DataError('INVALID_SELECTION','Select active local content')
            return r.update('node',node_id,{'state':'active'})
    def read_node(self,node_id,branch_id):
        self._scope(branch_id,node_id);r=self.repository;node=r.require('node',node_id);events=r.selection_records(node)
        result={'node':node,'narrative':None,'summary':None,'narrative_event_id':node['narrative_event_id'],'summary_event_id':node['summary_event_id']}
        for selection,key in (('narrative','literary_text'),('summary','summary')):
            if node[selection+'_event_id']:
                if selection=='narrative':
                    from .creative.narrative import read
                    result[selection]=read(r,node)
                else:result[selection]=events[node[selection+'_event_id']]['content'][key]
        return result
    def revise(self,p):
        r=self.repository
        with r.transaction():
            self._scope(p['branch_id'],p['node_id'])
            if r.require('node',p['node_id'])['state']!='active':raise DataError('NODE_NOT_ACTIVE','Revise a published node')
            r.update('node',p['node_id'],{'state':'updating'});result=self.create_event(p)
            r.update('node',p['node_id'],{'state':'active'})
            return {**result,'node':r.require('node',p['node_id'])}
    def cancel_event(self,event_id,branch_id):
        r=self.repository
        with r.transaction():
            node_id=r.owner(event_id)['node_id'];self._leaf_branch(node_id,branch_id);node=r.require('node',node_id)
            if node['state']=='active':r.update('node',node_id,{'state':'updating'})
            result=r.update('event',event_id,{'state':'cancelled'})
            if node['state']=='active':r.update('node',node_id,{'state':'active'})
            return result
    def cancel_node(self,node_id,branch_id):
        r=self.repository
        with r.transaction():
            self._leaf_branch(node_id,branch_id)
            if r.require('node',node_id)['node_type']=='root':raise DataError('ROOT_PROTECTED','Keep root')
            return r.update('node',node_id,{'state':'cancelled'})
    def delete_leaf(self,node_id,branch_id):
        r=self.repository
        with r.transaction():
            self._leaf_branch(node_id,branch_id)
            if r.require('node',node_id)['node_type']=='root':raise DataError('ROOT_PROTECTED','Keep root')
            context=r.deletion_context(node_id)
            if any(ref['relation_type']!='branch_head' for ref in context['external_references']):raise DataError('EXTERNAL_DEPENDENCY','External references prevent deletion')
            result=r.remove_scene(context);parent=context['predecessor_id']
            if parent and not r.has_successors(parent):r.assign_head(branch_id,parent)
            # A non-leaf predecessor gets no head; retain the inactive branch identity object.
            view=r.branch(branch_id)
            return {**result,'branch_id':branch_id,'head_node_id':view['head']['node_id'] if view['head'] else None,'branch_status':view['status']}
    def _query_events(self,p,object_ids=None):
        scope=self._scope(p['branch_id'],p.get('at_node_id'));filters=dict(p.get('filters') or {})
        for key in ('event_type','event_action','state'):
            if key in p:filters[key]=p[key]
        if p.get('event_types') is not None:filters['event_type']=p['event_types']
        return self.repository.events_on_path(scope['at_node_id'],object_ids=object_ids,filters=filters,fields=p.get('fields'),
            limit=p.get('limit',100),offset=p.get('offset',0),descending=p.get('descending',False),include_total=p.get('include_total',True))
    @staticmethod
    def _guard_relation(value):
        if value.get('relation_type') in ('branch_head','node_branch'):raise DataError('RESERVED_RELATION','Use branch/node workflows for head management; node_branch is removed')
    def execute(self,operation,p):
        # Kept as a programmatic facade for isolated import helpers, without a command if-chain.
        from script.util.runtime import current
        from script.workflow.dispatch import dispatch
        from types import SimpleNamespace
        context=SimpleNamespace(repository=self.repository,resources=current())
        context.execute=lambda request: dispatch(context,request['operation'],request['params'])
        return dispatch(context,operation,p)
