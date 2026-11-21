"""Normal historical reads and one isolated scripted opening; no agent E2E."""
from pathlib import Path
from tempfile import TemporaryDirectory
from shutil import copyfile
import json
from .inventory import load, stable, digest
from script.data.api import connect
from script.workflow.data.repositories import Repository
from script.workflow.pipeline.creative.projection import project
from script.workflow.pipeline.creative.actions import unpack
from script.workflow.pipeline.creative.presentation import export
from script.workflow.pipeline.history import read_node
from script.workflow.pipeline.creative.lifecycle import open_scene
from script.workflow.pipeline.creative.recall import recall, lookup
from script.workflow.pipeline.creative.common import context


def verify(plan,config,check_opening=True):
    repo=Repository(connect(config));source=Path(plan['source']);checked=[]
    try:
        actual_nodes=repo.records('node');assert {n['node_id'] for n in actual_nodes}==set(plan['node_order'])
        assert all(n['state']=='active' for n in actual_nodes)
        assert len([n for n in actual_nodes if n['node_type']=='root'])==1
        actual_branches=[o for o in repo.records('object') if o['object_type']=='branch']
        assert {o['object_id'] for o in actual_branches}=={b['branch_id'] for b in plan['branches']}
        for branch in plan['branches']:
            path=repo.ancestor_path(branch['head_node_id'])
            assert not repo.has_successors(branch['head_node_id'])
            assert repo.branch(branch['branch_id'])['head']['node_id']==branch['head_node_id']
            for node_id in path:
                expected=set(repo.ancestor_path(node_id));rows=repo.source_records(node_id)
                assert all(r['node_id'] in expected for r in rows)
                expected_ids={r['event']['event_id'] for r in plan['events'] if r['node_id'] in expected}
                assert {r['event']['event_id'] for r in rows}==expected_ids
                if plan['nodes'][node_id]['kind']=='scene':
                    prose=read_node(repo,{'branch_id':branch['branch_id'],'at_node_id':node_id,'node_id':node_id})['literary_text']
                    assert digest(prose.encode('utf8'))==plan['source_hashes']['nodes/'+node_id+'/narrative.md']
                    inp=repo.require('event',stable(plan['story_id'],'nodes/'+node_id+'/input.json',''))['content']
                    old=load(source/'nodes'/node_id/'input.json')
                    assert {k:v for k,v in inp.items() if k!='provenance'}==old
                projected=project(rows)
                # Control records are evaluated after scope filtering, never globally.
                adopted={r['event']['event_id'] for items in projected.values() for r in items}
                for row in rows:
                    if row['event']['event_action'] in ('replace','cancel'):
                        for target in unpack(row['event']['content'])[1]:assert target not in adopted
                checked.append({'branch_id':branch['branch_id'],'node_id':node_id,'source_count':len(rows)})
        for row in repo.records('event'):
            owner=repo.owner(row['event_id']);assert owner['node_id'] in plan['nodes']
            if row['event_type'] in ('director_packet','author_packet','director_archive'):
                allowed=set(repo.ancestor_path(owner['node_id']))
                for key in row['content'].get('event_ids',[]):assert repo.owner(key)['node_id'] in allowed
        snapshot=export(repo)
        assert snapshot['defaultBranchId']==plan['default_branch_id']
        assert len(snapshot['chapters'])==len(plan['node_order'])-1
        assert {b['id'] for b in snapshot['branches']}=={b['branch_id'] for b in plan['branches']}
        opening=[]
        if check_opening:
            cfg=load(config);db=Path(config).parent/cfg['location']
            for b in plan['branches']:
                with TemporaryDirectory(prefix='openstory-migration-opening-') as folder:
                    folder=Path(folder);copyfile(db,folder/'story.sqlite3')
                    (folder/'sqlite.json').write_text(json.dumps(cfg),encoding='utf8')
                    trial=Repository(connect(folder/'sqlite.json'))
                    try:
                        opened=open_scene(trial,{'branch_id':b['branch_id'],'mode':'normal','content':{
                            'raw_user_messages':[{'text':'迁移功能检查：继续当前故事。','source':'simulation'}]}})
                        result=recall(trial,{'node_id':opened['node_id'],'branch_id':b['branch_id'],'view':'full'})
                        fixed=context(trial,opened['node_id'],b['branch_id'])
                        assert fixed['history_node_id']==b['head_node_id']
                        assert result['previous_scene_prose']==(source/'nodes'/b['head_node_id']/'narrative.md').read_bytes().decode('utf8')
                        visible=set(trial.ancestor_path(b['head_node_id']))
                        assert all(r['node_id'] in visible for r in result['sources'])
                        assert 'player' in result['selected_character_ids']
                        opening.append({'branch_id':b['branch_id'],'source_count':len(result['sources']),
                                        'capsule_mode':result['capsule_mode'],'capsule_count':len(result['capsules'])})
                    finally:trial.close()
        return {'ok':True,'counts':repo.info()['counts'],'checked_cutoffs':checked,'opening_checks':opening,
                'default_branch_id':snapshot['defaultBranchId'],'chapter_count':len(snapshot['chapters'])}
    finally:repo.close()
