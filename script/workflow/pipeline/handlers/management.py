"""Thin management routes."""
from .. import management


def stories(c,p):return management.list_stories(c.data_root,p.get('environment'))
def info(c,p):return management.info(c.repository)
def story_state(c,p):return management.set_state(c.repository,p,'story_lifecycle')
def branches(c,p):return management.branches(c.repository)
def branch_state(c,p):return management.set_state(c.repository,p,'branch_lifecycle')
