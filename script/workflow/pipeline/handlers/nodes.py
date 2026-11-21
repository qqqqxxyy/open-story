"""Node lifecycle workflows reuse the existing business policies."""
from ..story import Operations
from ..creative.actions import from_request
def begin(c,p): return Operations(c.repository).begin(p)
def publish(c,p): return Operations(c.repository).publish(p['node_id'],p['branch_id'])
def read(c,p): return Operations(c.repository).read_node(p['node_id'],p['branch_id'])
def cancel(c,p): return Operations(c.repository).cancel_node(p['node_id'],p['branch_id'])
def delete_leaf(c,p): return Operations(c.repository).delete_leaf(p['node_id'],p['branch_id'])
def revise(c,p): return Operations(c.repository).revise(from_request(p))
