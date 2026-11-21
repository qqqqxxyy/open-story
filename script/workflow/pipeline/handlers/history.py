"""Thin history routes, with caller-supplied scope."""
from .. import history

def search(c,p):return history.search(c.repository,p)
def read(c,p):return history.read_node(c.repository,p)
def inspect(c,p):return history.inspect(c.repository,p)

def list_scenes(c,p):return history.list_scenes(c.repository,p)
