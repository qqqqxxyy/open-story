"""Record workflows and reserved relationship protections."""
from uuid import uuid4
from ..story import Operations

def create(context,p):
    record=dict(p['record'])
    if p['entity']=='relation':
        Operations._guard_relation(record)
        record.setdefault('relation_id','relation-'+uuid4().hex)
    return context.repository.create(p['entity'],record)
def get(context,p): return context.repository.get(p['entity'],p['record_id'])
def list_records(context,p):
    return context.repository.query(p['entity'],p.get('filters'),p.get('limit',100),p.get('offset',0),p.get('descending',False))
def update(context,p):
    if p['entity']=='relation': Operations._guard_relation(context.repository.require('relation',p['record_id']))
    return context.repository.update(p['entity'],p['record_id'],p['patch'])
def delete(context,p):
    if p['entity']=='relation': Operations._guard_relation(context.repository.require('relation',p['record_id']))
    return context.repository.delete(p['entity'],p['record_id'])
def ensure_object(context,p): return context.repository.ensure_object(p)
def create_relation(context,p):
    Operations._guard_relation(p)
    record=dict(p);record.setdefault('relation_id','relation-'+uuid4().hex)
    return context.repository.create('relation',record)
