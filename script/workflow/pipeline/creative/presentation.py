"""Read-only SQLite export and derived reader publication, outside SQL transactions."""
from pathlib import Path
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4
import json
import os
import shutil
import subprocess
from script.util.errors import ContractError
from script.util.runtime import current
from .common import settings, enabled, context, append, latest, identifier, messages
from .narrative import resolve


# Match JavaScript trimEnd exactly; normalize the revision, never stored prose.
_REVISION_TRAILING_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


def body_revision(text):
    normalized = text.replace("\r\n", "\n").rstrip(_REVISION_TRAILING_SPACE)
    return sha256(normalized.encode('utf8')).hexdigest()


def reader_material(source,metadata):
    tag=metadata.get('_manuscript',{})
    inputs=[m for event in source if event['event_type']=='user_input' and
        ('input_event_ids' not in tag or event['event_id'] in tag['input_event_ids']) for m in messages(event['content'])]
    director=tag.get('director_packet_event_id')
    brief=next((event['content'] for event in reversed(source) if event['event_type']=='director_packet'
        and (not director or event['event_id']==director)),{})
    return inputs,brief


def reader_content(node_id,turn,metadata,text,inputs,brief):
    return {'title':metadata.get('title','第 '+str(turn)+' 幕'),'narrative':text,'summary':metadata['summary'],
        'location':metadata.get('location',''),'time':metadata.get('time',''),
        'participants':metadata.get('participants',[]),'input':'\n\n'.join(message['text'] for message in inputs),
        'intent':brief.get('interpreted_intent',''),'display':{'key':'node:'+node_id,'revision':body_revision(text),'pending':False}}


def export(repository):
    nodes = repository.records('node')
    node_by_id = {node['node_id']: node for node in nodes}
    depths = {}
    def depth(node_id):
        if node_id not in depths:
            node = node_by_id[node_id]
            parent = node['predecessor_node_id']
            depths[node_id] = (depth(parent) if parent else 0)+(node['node_type'] != 'root')
        return depths[node_id]
    objects = repository.records('object')
    kinds = ['narrative', 'dialogue_fragment', 'author_reply', 'scene_summary', 'display_metadata',
             'user_input', 'director_packet', 'story_identity', 'story_setting']
    rows = [row for row in repository.source_records(None, all_nodes=True, event_types=kinds)
            if row['event']['event_action'] != 'summarize']
    events = {row['event']['event_id']: row['event'] for row in rows}
    local = {}
    for row in rows:
        local.setdefault(row['node_id'], []).append(row['event'])
    from .actions import unpack
    identity = next((row['event']['content'] for row in reversed(rows) if row['event']['event_type'] == 'story_identity'), {})
    story_id = identity.get('story_id', repository.identity()['database_id'])
    title = identity.get('title', story_id)
    if title == story_id:
        title_event = next((row['event']['content'] for row in rows if row['event']['event_type'] == 'story_setting' and row['event']['type_name'] == 'title'), None)
        title_event=unpack(title_event)[0]
        if isinstance(title_event, str):
            title = title_event
    branches = []
    for obj in objects:
        if obj['object_type'] != 'branch':
            continue
        branch = repository.branch(obj['object_id'])
        if branch['head']:
            branches.append({'id': obj['object_id'], 'name': obj['name'], 'headNodeId': branch['head']['node_id'],
                'status': branch['status'], 'nodeIds': repository.ancestor_path(branch['head']['node_id'])})
    chapters = []
    for node in nodes:
        if node['node_type'] == 'root' or node['state'] == 'cancelled' or not node['narrative_event_id']:
            continue
        source = local.get(node['node_id'], [])
        metadata = next((event['content'] for event in reversed(source) if event['event_type'] == 'display_metadata'), None)
        if metadata is None and node['summary_event_id']:
            metadata = events[node['summary_event_id']]['content']
        if metadata is None:
            continue
        text = resolve(events, node['narrative_event_id'])
        inputs,brief=reader_material(source,metadata)
        branch_ids = [branch['id'] for branch in branches if node['node_id'] in branch['nodeIds']]
        turn = depth(node['node_id'])
        chapters.append({'id': node['node_id'], 'storyId': story_id, 'turn': turn, 'file': '',
            **reader_content(node['node_id'],turn,metadata,text,inputs,brief),'raw':{},'timelineOrder':node['seq'],
            'creationIndex': turn, 'creationParentId': node['predecessor_node_id'], 'relation': 'continuation',
            'branchIds':branch_ids})
    from ..management import story_state
    if story_state(repository)=='archived':chapters=[]
    visible = {chapter['id'] for chapter in chapters}
    for branch in branches:
        branch['nodeIds'] = [key for key in branch['nodeIds'] if key in visible]
        branch['headNodeId'] = branch['nodeIds'][-1] if branch['nodeIds'] else ''
    branches = [branch for branch in branches if branch['headNodeId']]
    edges = [{'id': 'edge-'+chapter['id'], 'from': chapter['creationParentId'], 'to': chapter['id'], 'kind': 'timeline'}
             for chapter in chapters if chapter['creationParentId'] in visible]
    preferred = identity.get('default_branch_id')
    available = {branch['id'] for branch in branches}
    default = preferred if preferred in available else ('main' if 'main' in available else branches[0]['id'] if branches else 'main')
    return {'source_kind': 'open_story', 'syncedAt': datetime.now(timezone.utc).isoformat(),
        'slug': story_id, 'id': story_id, 'title': title, 'chapters': chapters, 'branches': branches,
        'defaultBranchId': default, 'warnings': [], 'graph': {'storyId': story_id,
            'entryNodeIds': [chapter['id'] for chapter in chapters if chapter['creationParentId'] not in visible], 'edges': edges}}


def _visible(snapshot):
    return {key:value for key,value in snapshot.items() if key != 'syncedAt'}


def sync(repository, params):
    if repository.in_transaction:
        raise ContractError('COMPOSITE_IN_BATCH','Publish derived reader files outside a batch transaction')
    snapshot = export(repository)
    cfg = settings()['display']
    display_project = (current().project_root/cfg['project_path']).resolve()
    output_root = Path(params['output_root']).resolve() if params.get('output_root') else display_project
    target = output_root/'story'/snapshot['id']/'story.json'
    previous = None
    try:previous=json.loads(target.read_text(encoding='utf8'))
    except (OSError,ValueError):pass
    old_chapters={item['id']:item for item in (previous or {}).get('chapters',[])}
    chapters={item['id']:item for item in snapshot['chapters']}
    changed=[key for key,value in chapters.items() if old_chapters.get(key)!=value]
    removed=[key for key in old_chapters if key not in chapters]
    snapshot_changed=previous is None or _visible(previous)!=_visible(snapshot)
    if snapshot_changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary=target.with_name('story-'+uuid4().hex+'.tmp')
        temporary.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        os.replace(temporary,target)
    html_path=output_root/'dist/index.html'
    marker_path=output_root/'dist/display-version.js'
    html_ready=False
    try:
        import re
        html=html_path.read_text(encoding='utf8')
        match=re.search(r'<script type="application/json" id="story-data">([\s\S]*?)</script>',html)
        embedded=json.loads(match.group(1)) if match else {}
        found=next((story for story in embedded.get('stories',[]) if story['id']==snapshot['id']),None)
        marker_text=marker_path.read_text(encoding='utf8')
        marker=json.loads(marker_text[marker_text.index('(')+1:marker_text.rindex(')')])
        revision=re.search(r'<meta name="story-display-revision" content="([a-f0-9]{64})">',html)
        versions=re.search(r'<script type="application/json" id="story-display-versions">([\s\S]*?)</script>',html)
        marker_ready=bool(isinstance(marker,dict) and revision and versions and marker.get('contentRevision')==revision.group(1)
                          and marker.get('storyRevisions')==json.loads(versions.group(1)))
        html_ready=found is not None and _visible(found)==_visible(snapshot) and marker_ready
    except (OSError,ValueError,KeyError):pass
    generate=params.get('generate',cfg['generate'])
    publication='unchanged' if not snapshot_changed and html_ready else 'snapshot_only'
    if generate and not html_ready:
        executable=shutil.which(cfg['node_executable']) or cfg['node_executable']
        call=subprocess.run([executable,str(display_project/'scripts/sync-snapshot.ts'),'--snapshot',str(target),
            '--output-root',str(output_root)],cwd=display_project,capture_output=True,text=True,encoding='utf8')
        if call.returncode:
            raise ContractError('DISPLAY_FAILED','Prose is saved; display generation failed: '+call.stderr.strip())
        publication='published';html_ready=True
    node=chapters.get(params.get('node_id'))
    return {'story_id':snapshot['id'],'snapshot_path':str(target),
        'html_path':str(html_path) if html_ready else None,'chapter_count':len(chapters),
        'publication_status':publication,'snapshot_changed':snapshot_changed,
        'changed_node_ids':changed,'removed_node_ids':removed,
        'node_revision':node['display']['revision'] if node else None}


def display(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    node = repository.require('node', ctx['node_id'])
    if not node['narrative_event_id']:
        raise ContractError('NARRATIVE_REQUIRED', 'Save complete prose before display')
    content = params['content']
    from . import manuscripts
    active=manuscripts.attempt(repository,ctx['node_id'])
    display_id=identifier('display',ctx['node_id'],active['attempt_id']) if active else identifier('display',ctx['node_id'])
    previous=repository.get('event',display_id)
    if active:
        content=dict(content)
        reply=manuscripts.packet(repository,ctx['node_id'])
        if not reply:raise ContractError('PACKET_NOT_FOUND','Complete the current manuscript before display')
        saved=previous['content'].get('_manuscript',{}) if previous else {}
        root=str(Path(params.get('output_root') or saved.get('output_root') or current().project_root/settings()['display']['project_path']).resolve())
        generate=params.get('generate',saved.get('html_required',settings()['display']['generate']))
        if saved and root!=saved['output_root']:
            raise ContractError('IDEMPOTENCY_CONFLICT','Restore this manuscript at its saved output root or use display-export')
        if saved:content['_manuscript']=saved
        else:
            from .common import local
            content['_manuscript']={'author_packet_event_id':reply['event_id'],'narrative_event_id':node['narrative_event_id'],
                'director_packet_event_id':reply['content']['director_packet_event_id'],
                'input_event_ids':[row['event']['event_id'] for row in local(repository,ctx['node_id'],['user_input'])],
                'output_root':root,'html_required':generate}
        params={**params,'output_root':root,'generate':generate}
    if previous is None:
        with repository.transaction():
            append(repository, ctx, 'display_metadata', ctx['node_id'], content,
                   display_id,select_as='summary')
    elif previous['content'] != content:
        raise ContractError('IDEMPOTENCY_CONFLICT', 'Display retry must preserve the saved metadata')
    return sync(repository, params)
