"""Stable data returned to pipeline; raw content is interpreted by pipeline."""
from typing import TypedDict

class EventOwner(TypedDict):
    node_id:str
    object_id:str
    relation:dict

class Reference(TypedDict):
    entity:str
    record_id:str
    relation_type:str

class DeletionContext(TypedDict):
    node_id:str
    predecessor_id:str|None
    event_ids:list[str]
    relation_ids:list[str]
    external_references:list[Reference]

class BranchView(TypedDict):
    branch:dict
    head:dict|None
    status:str
