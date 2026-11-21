"""Registered creative routes; host agents perform literary work outside the CLI."""
from ..creative import lifecycle, recall, handoff, business, presentation, capsule
from ..creative.common import context, enabled


def next_scene(c, p): return lifecycle.open_scene(c.repository, p)
def scene_status(c, p): return lifecycle.status(c.repository, p['node_id'], p.get('branch_id'),p.get('output_root'))
def author_bind(c, p): return lifecycle.bind(c.repository, p)
def scene_context(c, p): return recall.recall(c.repository, p)
def context_read(c, p): return recall.lookup(c.repository, p)
def director_save(c, p): return handoff.save_director(c.repository, p)
def director_read(c, p): return handoff.read_director(c.repository, p)
def author_save(c, p): return handoff.save_author(c.repository, p)
def author_read(c, p): return handoff.read_author(c.repository, p)
def dialogue_input(c, p): return lifecycle.dialogue_input(c.repository, p)
def dialogue_save(c, p): return handoff.save_turn(c.repository, p)
def dialogue_close(c, p):
    enabled()
    ctx = context(c.repository, p['node_id'], p.get('branch_id'))
    from script.util.errors import ContractError
    if ctx['mode'] != 'dialogue': raise ContractError('USE_NORMAL_REPLY', 'Not a dialogue scene')
    return handoff.close_dialogue(c.repository, ctx, p.get('content', {}))
def dialogue_read(c, p): return handoff.read_dialogue(c.repository, p)
def business_save(c, p): return business.save(c.repository, p)
def business_read(c, p): return business.read_records(c.repository, p)
def scene_display(c, p): return presentation.display(c.repository, p)
def scene_archive(c, p): return business.archive(c.repository, p)
def display_export(c, p): return presentation.sync(c.repository, p)

def capsule_check(c, p): return capsule.check(c.repository, p)
def capsule_read(c, p): return capsule.read(c.repository, p)
def capsule_save(c, p): return capsule.save(c.repository, p)


def scene_prepare(c,p):
    from ..creative.scenes import prepare
    return prepare(c.repository,p)

def scene_submit(c,p):
    from ..creative.scenes import submit
    return submit(c.repository,p)


def scene_accept(c,p):
    from ..creative.scenes import accept
    return accept(c.repository,p)

def scene_maintenance(c,p):
    from ..creative.maintenance import execute
    return execute(c.repository,p)
