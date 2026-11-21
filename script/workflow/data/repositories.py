"""Map stable workflow data requests to current storage records; never execute SQL."""
from .interface import StoryRepository
from script.data.base import DataStore
from script.data.contracts import DataError,make_id
from script.util.contracts import WORKFLOW,AGENT,validate

class Repository(StoryRepository):
    def __init__(self,store:DataStore):self._store=store
    def transaction(self):return self._store.transaction()
    def get(self,entity,record_id):return self._store.get(entity,record_id)
    def require(self,entity,record_id):return self._store.require(entity,record_id)
    def query(self,entity,filters=None,limit=100,offset=0,descending=False):return self._store.query(entity,filters,limit,offset,descending)
    def create(self,entity,record):return self._store.create(entity,record)
    def update(self,entity,record_id,patch):return self._store.update(entity,record_id,patch)
    def delete(self,entity,record_id):return self._store.delete(entity,record_id)
    def ensure_object(self,value):
        old=self.get('object',value['object_id'])
        if old:
            if (old['object_type'],old['object_key'])!=(value['object_type'],value['object_key']):raise DataError('IDENTITY_CONFLICT','Object identity differs')
            return old
        return self.create('object',value)
    def owner(self,event_id):
        rows=self._store.records('relation',{'relation_type':'event','key_type':'event','key_id':event_id},limit=1)
        if not rows:raise DataError('NOT_FOUND','Event ownership missing')
        row=rows[0];result={'node_id':row['target_node_id'],'object_id':row['target_object_id'],'relation':row}
        validate(result,'event_owner',WORKFLOW)
        return result
    def append_event(self,node_id,object_id,event):
        record=self.create('event',event)
        owner=self.create('relation',{'relation_id':make_id('ownership'),'relation_type':'event','key_type':'event',
            'key_id':record['event_id'],'target_node_id':node_id,'target_object_id':object_id})
        return {'event':record,'ownership':owner,'already_exists':False}
    def select(self,node_id,event_id,selection):return self.update('node',node_id,{selection+'_event_id':event_id})
    def selection_records(self,node):
        ids=[node[k] for k in ('narrative_event_id','summary_event_id') if node[k]]
        return {r['event_id']:r for r in self._store.records('event',{'event_id':ids})} if ids else {}
    def has_successors(self,node_id):return self._store.exists('node',{'predecessor_node_id':node_id})
    def branch(self,branch_id):
        branch=self.require('object',branch_id)
        if branch['object_type']!='branch':raise DataError('INVALID_BRANCH','Object is not a branch')
        rows=self._store.records('relation',{'relation_type':'branch_head','key_type':'object','key_id':branch_id},limit=1)
        head=self.require('node',rows[0]['target_node_id']) if rows else None
        result={'branch':branch,'head':head,'status':'active' if head else 'inactive'}
        validate(result,'branch_view',AGENT)
        return result
    def head_owner(self,node_id):
        rows=self._store.records('relation',{'relation_type':'branch_head','target_node_id':node_id},fields=['key_id'],limit=1)
        return self.branch(rows[0]['key_id']) if rows else None
    def assign_head(self,branch_id,node_id):
        rows=self._store.records('relation',{'relation_type':'branch_head','key_type':'object','key_id':branch_id},fields=['relation_id'],limit=1)
        if rows:return self.update('relation',rows[0]['relation_id'],{'target_node_id':node_id})
        return self.create('relation',{'relation_id':make_id('rel'),'relation_type':'branch_head','key_type':'object',
            'key_id':branch_id,'target_node_id':node_id})
    def ancestor_path(self,end_node_id):return self._store.ancestor_path(end_node_id)
    def is_ancestor(self,end_node_id,node_id):return self._store.is_ancestor(end_node_id,node_id)
    def events_on_path(self,end_node_id,**options):return self._store.events_on_path(end_node_id,**options)
    def records(self,entity,filters=None,fields=None,limit=None):return self._store.records(entity,filters,fields,limit)
    def descendants(self,node_id,include_anchor=True):return self._store.descendants(node_id,include_anchor)
    def range_deletion_context(self,node_ids):
        ids=set(node_ids)
        owners=self._store.records('relation',{'relation_type':'event','target_node_id':node_ids},fields=['key_id']) if ids else []
        events=[row['key_id'] for row in owners];owned=set(events)
        refs=self._store.references(node_ids=node_ids,event_ids=events)
        external=[];branches=[]
        for row in refs['relations']:
            inside=(row['key_type']=='node' and row['key_id'] in ids) or (row['key_type']=='event' and row['key_id'] in owned)
            if row['relation_type']=='branch_head':branches.append(row['key_id'])
            elif not inside:external.append({'entity':'relation','record_id':row['relation_id']})
        external.extend({'entity':'node','record_id':row['node_id']} for row in refs['nodes'] if row['node_id'] not in ids)
        result={'event_ids':events,'relation_ids':[row['relation_id'] for row in refs['relations']],
                'branch_ids':sorted(set(branches)),'external_references':external}
        validate(result,'range_deletion_context',WORKFLOW)
        return result
    def remove_range(self,context,node_ids):
        self._store.delete_many('relation',context['relation_ids'])
        for node_id in node_ids:self._store.delete_many('node',[node_id])
        self._store.delete_many('event',context['event_ids'])
    def source_records(self,end_node_id,**options):return self._store.source_records(end_node_id,**options)
    def max_sequence(self,entity):return self._store.max_sequence(entity)
    def node_events(self,node_id,**options):return self._store.events_for('node',node_id,**options)
    def deletion_context(self,node_id):
        node=self.require('node',node_id)
        owners=self._store.records('relation',{'relation_type':'event','target_node_id':node_id},fields=['key_id'])
        events=[r['key_id'] for r in owners]
        refs=self._store.references(node_ids=[node_id],event_ids=events)
        owned=set(events);external=[]
        for row in refs['relations']:
            inside=(row['key_type']=='node' and row['key_id']==node_id) or (row['key_type']=='event' and row['key_id'] in owned)
            if not inside:external.append({'entity':'relation','record_id':row['relation_id'],'relation_type':row['relation_type']})
        external += [{'entity':'node','record_id':row['node_id'],'relation_type':'node_pointer'} for row in refs['nodes'] if row['node_id']!=node_id]
        result={'node_id':node_id,'predecessor_id':node['predecessor_node_id'],'event_ids':events,
            'relation_ids':[r['relation_id'] for r in refs['relations']],'external_references':external}
        validate(result,'deletion_context',WORKFLOW)
        return result
    def remove_scene(self,context):
        self._store.delete_many('relation',context['relation_ids'])
        self._store.delete_many('node',[context['node_id']])
        self._store.delete_many('event',context['event_ids'])
        return {'node_id':context['node_id'],'deleted_events':len(context['event_ids']),'deleted_relations':len(context['relation_ids'])}
    @property
    def in_transaction(self):return self._store.in_transaction
    def identity(self):return {**{k:self._store.config[k] for k in ('database_id','backend')},'skill_version':self._store.skill_version}
    def info(self):return {'database_id':self._store.config['database_id'],'backend':self._store.config['backend'],
        'counts':{k:self.query(k,limit=1)['total'] for k in ('node','object','event','relation')}}
    def close(self):self._store.close()
