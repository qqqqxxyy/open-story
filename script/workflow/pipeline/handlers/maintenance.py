"""Thin range-maintenance routes."""
from .. import maintenance

def delete(c,p):return maintenance.execute(c.repository,p)
def rewrite(c,p):return maintenance.execute(c.repository,p,rewrite=True)
