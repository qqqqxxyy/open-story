"""Branch identity, head and path workflows."""
from ..story import Operations
def fork(c,p): return Operations(c.repository).fork(p)
def read(c,p): return c.repository.branch(p['branch_id'])
def scope(c,p):
    result=Operations(c.repository)._scope(p['branch_id'],p.get('at_node_id'))
    return {**result,'node_ids':c.repository.ancestor_path(result['at_node_id'])}
def node_branch(c,p):
    c.repository.require('node',p['node_id'])
    return None if c.repository.has_successors(p['node_id']) else Operations(c.repository)._leaf_branch(p['node_id'])
