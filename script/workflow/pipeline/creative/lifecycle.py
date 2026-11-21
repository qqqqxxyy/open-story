"""Open/resume one scene; host author identities are supplied, never invented."""
from copy import deepcopy
from uuid import uuid4
from script.workflow.data.creative import CreativeRepository
from script.util.errors import ContractError
from ..story import Operations
from .common import enabled, context, identifier, append, latest, local, messages, settings


def status(repository, node_id, branch_id=None, output_root=None):
    ctx = context(repository, node_id, branch_id)
    node = repository.require('node', node_id)
    rows = local(repository, node_id)
    latest_by_kind = {row['event']['event_type']: row['event'] for row in rows}
    binding_rows = CreativeRepository(repository).sources(node_id, event_types=['author_binding'])
    binding = next((row['event']['content'] for row in reversed(binding_rows)
                    if row['event']['content']['branch_id'] == ctx['branch_id']), None)
    reply = latest_by_kind.get('author_packet')
    display = latest_by_kind.get('display_metadata')
    handoff = latest_by_kind.get('director_packet')
    from pathlib import Path
    from .presentation import reader_content,reader_material
    from .narrative import resolve
    import json
    from script.util.runtime import current
    output_root=output_root or (display['content'].get('_manuscript',{}).get('output_root') if display else None)
    reader=Path(output_root) if output_root else (current().project_root/settings()['display']['project_path']).resolve()
    public_id=repository.identity()['database_id']
    root_identity=next((row['event']['content'] for row in CreativeRepository(repository).sources(ctx['history_node_id'],event_types=['story_identity'])),{})
    public_id=root_identity.get('story_id',public_id)
    snapshot_ready=False;html_ready=False
    if display and node['narrative_event_id']:
        body=resolve({row['event']['event_id']:row['event'] for row in rows},node['narrative_event_id'])
        inputs,brief=reader_material([row['event'] for row in rows],display['content'])
        expected=reader_content(node_id,len(repository.ancestor_path(node_id))-1,display['content'],body,inputs,brief)
        try:
            snapshot=json.loads((reader/'story'/public_id/'story.json').read_text(encoding='utf8'))
            snapshot_ready=any(chapter['id']==node_id and all(chapter.get(k)==v for k,v in expected.items()) for chapter in snapshot['chapters'])
            html=(reader/'dist/index.html').read_text(encoding='utf8')
            import re
            match=re.search(r'<script type="application/json" id="story-data">([\s\S]*?)</script>',html)
            embedded=json.loads(match.group(1)) if match else {}
            html_ready=snapshot_ready and any(chapter.get('id')==node_id and all(chapter.get(k)==v for k,v in expected.items()) for story in embedded.get('stories',[])
                if story.get('id')==public_id for chapter in story.get('chapters',[]))
        except (OSError,ValueError,KeyError):pass
    from . import manuscripts
    active=manuscripts.attempt(repository,node_id)
    if active:
        reply=manuscripts.packet(repository,node_id)
        if not manuscripts.display_matches(repository,node_id,reply):snapshot_ready=False;html_ready=False
    stage = 'complete' if node['state'] == 'active' else 'cancelled' if node['state'] == 'cancelled' else (
        'awaiting_archive' if display else 'awaiting_display' if reply else
        'dialogue_open' if ctx['mode'] == 'dialogue' and handoff else 'awaiting_author' if handoff else 'preparing')
    if active and node['state']!='cancelled':
        adopted=manuscripts.adoption(repository,node_id)
        if adopted:
            if latest(repository,node_id,'scene_maintenance_complete'):stage='complete'
            elif latest(repository,node_id,'director_archive'):stage='accepted_pending_capsules'
            else:stage='accepted_pending_archive'
        elif manuscripts.display_matches(repository,node_id,reply) and snapshot_ready and (not display['content'].get('_manuscript',{}).get('html_required') or html_ready):stage='awaiting_feedback'
        elif reply:stage='awaiting_display'
        else:stage='dialogue_open' if ctx['mode']=='dialogue' and handoff and active['kind']=='initial' else 'awaiting_author' if handoff else 'preparing'
    return {'node_id': node_id, 'branch_id': ctx['branch_id'], 'mode': ctx['mode'], 'status': stage,
            'history_node_id': ctx['history_node_id'], 'raw_input_event_ids': [row['event']['event_id'] for row in rows if row['event']['event_type'] == 'user_input'],
            'director_handoff_event_id': handoff['event_id'] if handoff else None,
            'author_reply_event_id': reply['event_id'] if reply else None,
            'narrative_event_id': node['narrative_event_id'], 'display_event_id': display['event_id'] if display else None,
            'author_binding': binding, 'published': node['state'] == 'active',
            'display_snapshot_available':snapshot_ready,'display_html_available':html_ready}


def open_scene(repository, params, origin=None):
    enabled()
    branch_id = params['branch_id']
    from ..management import permit_write
    permit_write(repository,branch_id)
    branch = repository.branch(branch_id)
    head = branch['head']
    if head is None:
        raise ContractError('BRANCH_INACTIVE', 'Branch has no head')
    supplied_node = params.get('node_id')
    node_id = supplied_node or (head['node_id'] if head['state'] == 'creating' else 'node-'+uuid4().hex)
    event_id = identifier('scene', node_id)
    old = repository.get('event', event_id)
    raw = messages(params['content'])
    if old:
        ctx = context(repository, node_id, branch_id)
        inputs = CreativeRepository(repository).referenced(ctx, ctx['raw_input_event_ids'])
        original = [message for row in inputs for message in messages(row['event']['content'])]
        if original != raw or ctx['mode'] != params['mode']:
            raise ContractError('SCENE_OPEN', 'An unfinished scene exists; use scene-status or dialogue-input, not a new scene-next')
        return status(repository, node_id, branch_id)
    with repository.transaction():
        if head['state'] == 'creating':
            # A branch-fork has already created its draft: adopt that draft without another node.
            if head['narrative_event_id'] or local(repository, head['node_id']):
                raise ContractError('SCENE_OPEN', 'Existing draft has content without a creative context')
            if supplied_node and supplied_node != head['node_id']:
                raise ContractError('SCENE_OPEN', 'Use the existing branch draft')
            node_id = head['node_id']
            parent = head['predecessor_node_id']
            event_id = identifier('scene', node_id)
        else:
            parent = head['node_id']
            Operations(repository).begin({'node_id': node_id, 'branch_id': branch_id})
        if parent is None or repository.require('node', parent)['state'] != 'active':
            raise ContractError('PREDECESSOR_INACTIVE', 'Creative history must end at an active parent')
        ctx = {'node_id': node_id, 'branch_id': branch_id, 'mode': params['mode'],
               'history_node_id': parent, 'history_event_seq': repository.max_sequence('event'),
               'previous_narrative_event_id': repository.require('node',parent)['narrative_event_id'],
               'previous_summary_event_id': repository.require('node',parent)['summary_event_id'],
               'raw_input_event_ids': []}
        event = append(repository, ctx, 'user_input', node_id, {'raw_user_messages': raw},
                       identifier('input', node_id, '0'))
        ctx['raw_input_event_ids'].append(event['event_id'])
        if origin:ctx['rewrite_origin']=origin
        value = {key: value for key, value in ctx.items() if key != 'node_id'}
        append(repository, ctx, 'scene_context', node_id, value, event_id)
    return status(repository, node_id, branch_id)


def bind(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    value = {'session_id': params['session_id'], 'agent_id': params['agent_id'], 'branch_id': ctx['branch_id']}
    previous = status(repository, ctx['node_id'])['author_binding']
    if previous == value:
        return {'binding': value, 'already_exists': True}
    from .common import writable
    writable(repository, ctx)
    event = append(repository, ctx, 'author_binding', ctx['branch_id'], value)
    return {'binding': value, 'event_id': event['event_id'], 'already_exists': False}


def dialogue_input(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    if ctx['mode'] != 'dialogue' or repository.require('node', ctx['node_id'])['narrative_event_id']:
        raise ContractError('DIALOGUE_CLOSED', 'Use an open dialogue scene')
    raw = messages(params['content'])
    rows = local(repository, ctx['node_id'], ['user_input', 'dialogue_fragment'])
    inputs = [row['event'] for row in rows if row['event']['event_type'] == 'user_input']
    replied = {row['event']['content']['turn_id'] for row in rows if row['event']['event_type'] == 'dialogue_fragment'}
    pending = [item for item in inputs if item['event_id'] not in replied]
    if pending:
        last = pending[-1]
        if messages(last['content']) != raw:
            raise ContractError('TURN_PENDING', 'Reply to the existing dialogue input before adding another')
        event = last
    else:
        from .common import writable
        writable(repository, ctx)
        event = append(repository, ctx, 'user_input', ctx['node_id'], {'raw_user_messages': raw}, params.get('turn_id'))
    return {'node_id': ctx['node_id'], 'turn_id': event['event_id'], 'raw_user_messages': raw,
            'mode': 'dialogue', 'author_binding': status(repository, ctx['node_id'])['author_binding']}
