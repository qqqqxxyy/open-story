"""Event and scoped recall workflows; queries remain database-composed."""
from ..story import Operations
from ..creative.actions import from_request
def create(c,p): return Operations(c.repository).create_event(from_request(p))
def cancel(c,p): return Operations(c.repository).cancel_event(p['event_id'],p['branch_id'])
def object_events(c,p):
    c.repository.require('object',p['object_id'])
    return Operations(c.repository)._query_events(p,[p['object_id']])
def query(c,p): return Operations(c.repository)._query_events(p,p.get('object_ids'))
def node_events(c,p):
    Operations(c.repository)._scope(p['branch_id'],p['node_id'])
    filters=dict(p.get('filters') or {})
    for key in ('event_type','event_action','state'):
        if key in p: filters[key]=p[key]
    return c.repository.node_events(p['node_id'],filters=filters,limit=p.get('limit',100),offset=p.get('offset',0),descending=p.get('descending',False))
