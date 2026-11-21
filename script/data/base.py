"""Storage contracts and shared structural rules, without story decision logic."""
from abc import ABC,abstractmethod
from contextlib import AbstractContextManager
from typing import Any, Literal, TypedDict
import copy
from .contracts import DATA,IDS,DataError,prepare,validate,validate_relation,now

Entity=Literal['node','object','event','relation']
Record=dict[str,Any]
class Page(TypedDict):
    items:list[Record]
    total:int
    offset:int
    next_offset:int|None


class QueryPage(TypedDict):
    items:list[Record]
    total:int|None
    offset:int
    next_offset:int|None

class ReferenceSet(TypedDict):
    relations:list[Record]
    nodes:list[Record]

class DataStore(ABC):
    def __init__(self,config):
        self.config=config
        self._depth=0
        self._affected_events=set()

    @property
    def in_transaction(self):
        return self._depth > 0

    @property
    def skill_version(self):
        raise NotImplementedError('Database version is provided by the active backend')

    @abstractmethod
    def initialize(self)->None:...
    @abstractmethod
    def transaction(self)->AbstractContextManager['DataStore']:...
    @abstractmethod
    def get(self,entity:Entity,record_id:str)->Record|None:...
    @abstractmethod
    def query(self,entity:Entity,filters:dict|None=None,limit:int=100,offset:int=0,descending:bool=False)->Page:...
    @abstractmethod
    def events_for(self,owner_kind:Literal['node','object'],owner_id:str,filters:dict|None=None,
                   node_ids:list[str]|None=None,limit:int=100,offset:int=0,descending:bool=False)->Page:...
    @abstractmethod
    def close(self)->None:...
    @abstractmethod
    def _insert(self,entity,value):...
    @abstractmethod
    def _replace(self,entity,value):...
    @abstractmethod
    def _remove(self,entity,record_id):...

    @abstractmethod
    def records(self,entity:Entity,filters:dict|None=None,fields:list[str]|None=None,limit:int|None=None)->list[Record]:...
    @abstractmethod
    def exists(self,entity:Entity,filters:dict)->bool:...
    @abstractmethod
    def ancestor_path(self,end_node_id:str)->list[str]:...
    @abstractmethod
    def is_ancestor(self,end_node_id:str,node_id:str)->bool:...
    @abstractmethod
    def events_on_path(self,end_node_id:str,object_ids:list[str]|None=None,filters:dict|None=None,fields:list[str]|None=None,
                       limit:int=100,offset:int=0,descending:bool=False,include_total:bool=True)->QueryPage:...
    @abstractmethod
    def references(self,node_ids:list[str]=(),event_ids:list[str]=(),object_ids:list[str]=())->ReferenceSet:...
    @abstractmethod
    def delete_many(self,entity:Entity,record_ids:list[str])->int:...

    def descendants(self,node_id,include_anchor=True):
        raise NotImplementedError('Descendant query is implemented by SQLite')

    def source_records(self,end_node_id,current_node_id=None,event_ids=None,object_ids=None,event_types=None,seq_max=None,all_nodes=False):
        raise NotImplementedError('Source mapping is implemented by SQLite')

    def max_sequence(self,entity):
        raise NotImplementedError('Sequence lookup is implemented by SQLite')

    def all(self,entity,filters=None):
        offset=0
        while True:
            p=self.query(entity,filters,limit=1000,offset=offset)
            yield from p['items']
            if p['next_offset'] is None:break
            offset=p['next_offset']

    def require(self,entity,record_id):
        value=self.get(entity,record_id)
        if value is None:raise DataError('NOT_FOUND',entity+': '+record_id)
        return value

    def relations_for(self,entity,record_id):
        return self.references(**{entity+'_ids':[record_id]})['relations']

    def node_references(self,entity,record_id):
        return self.references(**{entity+'_ids':[record_id]})['nodes']

    def require_exists(self,entity,record_id):
        if not self.exists(entity,{IDS[entity]:record_id}):raise DataError('NOT_FOUND',entity+': '+record_id)

    def _check_relation(self,value):
        validate_relation(value)
        self.require_exists(value['key_type'],value['key_id'])
        for kind in ('node','event','object'):
            if value['target_'+kind+'_id'] is not None:self.require_exists(kind,value['target_'+kind+'_id'])
        if value['relation_type']=='event':
            others=self.records('relation',{'relation_type':'event','key_type':'event','key_id':value['key_id']},fields=['relation_id'],limit=1)
            if any(r['relation_id']!=value['relation_id'] for r in others):
                raise DataError('OWNERSHIP_EXISTS','An event has exactly one ownership')

    def _check_node(self,value):
        for field,kind in (('predecessor_node_id','node'),('narrative_event_id','event'),('summary_event_id','event')):
            if value[field] is not None:self.require_exists(kind,value[field])

    def create(self,entity:Entity,record:Record)->Record:
        with self.transaction():
            value=prepare(entity,copy.deepcopy(record))
            record_id=value[IDS[entity]]
            if self.get(entity,record_id) is not None:raise DataError('ALREADY_EXISTS',entity+': '+record_id)
            if entity=='relation':self._check_relation(value)
            if entity=='node':self._check_node(value)
            value.update(created_time=now(),modified_time=now())
            result=self._insert(entity,value)
            validate(result,entity)
            if entity=='event':self._affected_events.add(record_id)
            if entity=='relation' and value['relation_type']=='event':self._affected_events.add(value['key_id'])
            return result

    def update(self,entity:Entity,record_id:str,patch:Record)->Record:
        mutable={'node':{'state','narrative_event_id','summary_event_id'},'object':{'name','object_key'},'event':{'state'},'relation':{'state'}}
        with self.transaction():
            old=self.require(entity,record_id)
            allowed=mutable[entity]
            if entity=='relation' and old['relation_type']=='branch_head':allowed={'target_node_id'}
            if not patch or set(patch)-allowed:raise DataError('IMMUTABLE_FIELD','Only '+','.join(sorted(allowed))+' may be updated')
            value={**old,**copy.deepcopy(patch),'modified_time':now()}
            validate(value,entity)
            if entity=='relation':self._check_relation(value)
            if entity=='node':self._check_node(value)
            self._replace(entity,value)
            return value

    def delete(self,entity:Entity,record_id:str)->Record:
        with self.transaction():
            value=self.require(entity,record_id)
            if entity!='relation':
                refs=self.references(**{entity+'_ids':[record_id]})
                if refs['relations'] or refs['nodes']:
                    raise DataError('REFERENCED','Remove references before deleting a record')
            else:
                if value['relation_type']=='event':self._affected_events.add(value['key_id'])
            self._remove(entity,record_id)
            return value

    def _validate_ownership(self):
        for event_id in self._affected_events:
            if self.get('event',event_id) is not None:
                rows=list(self.all('relation',{'relation_type':'event','key_type':'event','key_id':event_id}))
                if len(rows)!=1:raise DataError('MISSING_OWNERSHIP','Create event and ownership in the same transaction')
