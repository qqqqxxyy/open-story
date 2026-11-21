"""Isolated import adapter, outside ordinary business persistence."""
from ..story import Operations
def import_sample(context,params):
    from script.compat.v5_sample import import_sample as run
    return run(Operations(context.repository),params['source_story'])
