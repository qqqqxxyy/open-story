"""Normal file migration, path visibility, business conversion and reader export."""
from pathlib import Path
import json
import tempfile
import unittest
from copy import deepcopy
from hashlib import sha256
from common import REPO
from script.cli.bootstrap import bootstrap
from script.compat.file_story.convert import plan
from script.compat.file_story.import_service import install
from script.compat.file_story.verify import verify
from script.data.api import connect
from script.workflow.data.repositories import Repository
from script.workflow.pipeline.creative.projection import project
from script.workflow.pipeline.creative.actions import unpack
from script.workflow.pipeline.creative.presentation import export
from script.workflow.pipeline.story import Operations
from script.workflow.pipeline.creative.lifecycle import open_scene
from script.workflow.pipeline.creative.recall import lookup
from script.util.errors import ContractError


class Migration(unittest.TestCase):
    backend='sqlite'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='openstory-file-migration-')
        self.base=Path(self.temp.name);self.source=self.base/'source'
        bootstrap(logging_enabled=False)
        self.write('story.json',{'version':4,'id':'fixture','title':'TEST_MIGRATION','protagonist':{'name':'TEST_PLAYER'},'default_branch_id':'main'})
        base={'version':4,'story_id':'fixture','node_id':'node-root','canon_revision_id':'canon-v1',
              'scene':None,'world_facts':{},'characters':{},'relationships':{},'character_memories':[],
              'historical_traces':{},'open_threads':{},'director':{},'author_notes':'ROOT_NOTE','recent_path_summaries':[]}
        self.write('canon/baselines/initial.json',{'state':base})
        self.node('node-root',None,'main',{},'',snapshot=base)
        first={'scene':{'summary':'FIRST','time':'TIME','location':'PLACE','participants':['player']},
               'character_upserts':[{'id':'player','name':'TEST_PLAYER','current':{'old':'KEEP'},'traits':'STEADY'}],
               'facts_add':[{'id':'job','claim':'OLD_TASK'}],
               'memories_add':[{'character_id':'player','kind':'observed','claim':'FIRST_MEMORY','source':'TEST'}],
               'threads_open':[{'id':'thread','text':'OPEN_THREAD'}]}
        self.node('node-a1','node-root','main',first,'FIRST_PROSE\r\nSECOND_LINE')
        second={'scene':{'summary':'SECOND','time':'TIME','location':'PLACE'},
                'character_upserts':[{'id':'player','current':{'new':'ADD'}}],
                'facts_replace':[{'id':'job','new_fact':{'id':'done','claim':'NEW_TASK'},'reason':'DONE'}],
                'threads_close':['thread']}
        self.node('node-a2','node-a1','main',second,'SECOND_PROSE')
        alternative=deepcopy(first);alternative['scene']['summary']='ALTERNATIVE'
        alternative['facts_add'][0]['claim']='OTHER_BRANCH_TASK'
        alternative['memories_add'][0]['claim']='OTHER_BRANCH_MEMORY'
        self.node('node-b1','node-root','alt',alternative,'ALTERNATIVE_PROSE')
        for key,head in [('main','node-a2'),('alt','node-b1')]:
            self.write('graph/branches/'+key+'.json',{'branch_id':key,'name':key,'head_node_id':head,'forked_from_node_id':'node-root'})
        self.write('.system/backstage/alt/truths/test.json',{'revisions':[
            {'truth_id':'test','revision':1,'status':'candidate','proposition':'ALT_SECRET',
             'effective_at_node_id':'node-root','causal_mechanism':'DESIGN'}]})
        self.write('.system/exchanges/alt/messages/request.json',{'kind':'scene.request','message_id':'request',
            'scope':{'branch_id':'alt','expected_head':'node-root','turn_id':'turn-node-b1'},
            'director_brief':{'scene_need':'NEED'}})
        self.write('.system/exchanges/alt/messages/reply.json',{'kind':'author.reply','message_id':'reply','reply_to':'request',
            'scope':{'branch_id':'alt','expected_head':'node-root','turn_id':'turn-node-b1'},
            'literary_text':'ALTERNATIVE_PROSE','editorial_feedback':{'occurred':['TEST']}})
        self.write('.system/drafts/completed.json',{'branch_id':'main','expected_head':'node-root','status':'complete',
            'fragments':[{'fragment_id':'historical-transcript','text':'用户：RAW_EARLY_TURN\n正文：FIRST_PROSE\n技术标记：OLD'}]})
        self.plan=plan(self.source,['main','alt'],'alt')
        self.target=self.base/'online/fixture'
        result=install(self.plan,self.target)
        self.repo=Repository(connect(result['config_path']))

    def tearDown(self):
        self.repo.close();self.temp.cleanup();bootstrap()

    def write(self,file,value):
        target=self.source/file;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')

    def node(self,key,parent,branch,delta,body,snapshot=None):
        meta={'node_id':key,'kind':'root' if parent is None else 'scene','creation_parent_id':parent,
              'origin_branch_id':branch,'created_at':'2026-01-01T00:00:00Z','state_mode':'reset' if parent is None else 'inherit',
              'state_base':{'id':'initial'} if parent is None else None}
        self.write('nodes/'+key+'/meta.json',meta)
        self.write('nodes/'+key+'/delta.json',delta)
        self.write('nodes/'+key+'/input.json',{} if parent is None else {'turn_id':'turn-'+key,
            'raw_user_messages':[{'text':'RAW\n  INPUT：'+key,'source':'simulation'}],'raw_player_input':'RAW\n  INPUT：'+key})
        folder=self.source/'nodes'/key
        (folder/'narrative.md').write_bytes(body.encode('utf8'))
        if snapshot:self.write('nodes/'+key+'/snapshot.json',snapshot)
        hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name!='manifest.json'}
        self.write('nodes/'+key+'/manifest.json',{'files':hashes})

    def test_one_root_multiple_first_scenes_and_only_real_leaf_heads(self):
        nodes=self.repo.records('node');heads=self.repo.records('relation',{'relation_type':'branch_head'})
        self.assertEqual(len([n for n in nodes if n['node_type']=='root']),1)
        self.assertEqual({n['node_id'] for n in nodes if n['predecessor_node_id']=='node-root'},{'node-a1','node-b1'})
        self.assertEqual({h['target_node_id'] for h in heads},{'node-a2','node-b1'})
        self.assertFalse(self.repo.records('relation',{'relation_type':'node_branch'}))

    def test_profile_deep_merge_fact_replacement_closure_and_sibling_isolation(self):
        before=project(self.repo.source_records('node-a1'));after=project(self.repo.source_records('node-a2'))
        alt=project(self.repo.source_records('node-b1'))
        self.assertEqual(before['world_fact'][0]['event']['content']['text'],'OLD_TASK')
        self.assertEqual(after['world_fact'][0]['event']['content']['text'],'NEW_TASK')
        self.assertEqual(alt['world_fact'][0]['event']['content']['text'],'OTHER_BRANCH_TASK')
        self.assertEqual(after['role_profile'][0]['event']['content']['current'],{'old':'KEEP','new':'ADD'})
        self.assertEqual(after['role_profile'][0]['event']['content']['name'],'TEST_PLAYER')
        self.assertEqual(len(before['thread']),1);self.assertFalse(after['thread']);self.assertEqual(len(alt['thread']),1)
        self.assertEqual([r['event']['content']['claim'] for r in alt['role_memory']],['OTHER_BRANCH_MEMORY'])

    def test_backend_production_owner_and_author_feedback_source_pair(self):
        self.assertFalse(project(self.repo.source_records('node-root'))['truth'])
        self.assertFalse(project(self.repo.source_records('node-a2'))['truth'])
        self.assertEqual(project(self.repo.source_records('node-b1'))['truth'][0]['event']['content']['text'],'ALT_SECRET\nDESIGN')
        packets=self.repo.records('event',{'event_type':'author_packet'})
        self.assertEqual(len(packets),1)
        self.assertEqual(packets[0]['content']['legacy']['editorial_feedback'],{'occurred':['TEST']})
        self.assertEqual(self.repo.require('event',packets[0]['content']['source_packet_event_id'])['event_type'],'director_packet')
        self.assertNotIn('literary_text',packets[0]['content']['legacy'])

    def test_declared_default_overrides_existing_main_and_complete_scripted_opening(self):
        self.assertEqual(export(self.repo)['defaultBranchId'],'alt')
        result=verify(self.plan,self.target/'sqlite.json')
        self.assertTrue(result['ok']);self.assertEqual(len(result['opening_checks']),2)
        self.assertEqual(self.repo.info()['counts']['node'],4)

    def test_distinct_historical_transcript_keeps_original_early_input_without_fake_turns(self):
        records=self.repo.records('event',{'event_type':'legacy_dialogue_record'})
        self.assertEqual(len(records),1)
        fragment=records[0]['content']['fragments'][0]
        self.assertIn('RAW_EARLY_TURN',fragment['text'])
        self.assertEqual(fragment['representation'],'original-historical-transcript')
        self.assertEqual(self.repo.owner(records[0]['event_id'])['node_id'],'node-a1')
        self.assertFalse(self.repo.records('event',{'event_type':'dialogue_fragment'}))

    def test_historical_fork_lookup_keeps_later_design_outside_creative_scope(self):
        secret=self.repo.records('event',{'event_type':'truth'})[0]['event_id']
        Operations(self.repo).fork({'from_node_id':'node-root','branch_id':'new-opening','node_id':'node-new'})
        opened=open_scene(self.repo,{'branch_id':'new-opening','mode':'normal','content':{
            'raw_user_messages':[{'text':'从共同起点展开另一种开局。','source':'simulation'}]}})
        with self.assertRaises(ContractError) as rejected:
            lookup(self.repo,{'node_id':opened['node_id'],'branch_id':'new-opening','event_ids':[secret]})
        self.assertEqual(rejected.exception.code,'SOURCE_NOT_VISIBLE')


class PolicyMigration(unittest.TestCase):
    """Normal policy plan -> import -> historical queries, in isolated SQLite stores."""
    backend = 'sqlite'

    def setUp(self):
        from script.compat.file_story.policy import apply_policy
        self.fixture = Migration('test_one_root_multiple_first_scenes_and_only_real_leaf_heads')
        self.fixture.setUp()
        self.source = self.fixture.source
        first = json.loads((self.source/'nodes/node-a1/delta.json').read_text(encoding='utf8'))
        first['facts_add'].append({'id': 'old-rule', 'claim': 'HISTORICAL_CREATIVE_NOTE'})
        self.fixture.write('nodes/node-a1/delta.json', first)
        # Rebuild this source node's manifest after a normal fixture edit.
        folder = self.source/'nodes/node-a1'
        hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'manifest.json'}
        self.fixture.write('nodes/node-a1/manifest.json', {'files': hashes})
        self.legacy = self.fixture.base/'legacy'
        (self.legacy/'state').mkdir(parents=True)
        self.commits = []
        for i, node in enumerate(('node-a1', 'node-a2', 'node-b1'), 1):
            old = json.loads((self.source/'nodes'/node/'input.json').read_text(encoding='utf8'))
            self.commits.append({'turn_id': old['turn_id'], 'raw_player_input': old['raw_player_input'],
                                 'committed_at': '2025-09-0'+str(i)+'T12:00:00Z'})
        (self.legacy/'state/events.jsonl').write_text('\n'.join(json.dumps(c) for c in self.commits)+'\n', encoding='utf8')
        (self.legacy/'state/runtime.json').write_text(json.dumps({'director': {'story_phase': 'closing',
            'last_progress': 'FINAL_DIRECTOR_STATE'}}), encoding='utf8')
        self.policy = {'story_id': 'fixture', 'fact_topics': [{'key': 'employment', 'name': 'WORK_TOPIC',
                       'fact_ids': ['job', 'done']}], 'archive_fact_ids': ['old-rule'],
                       'strip_node_metadata_fields': ['created_at'], 'legacy': {
                       'commit_file': 'state/events.jsonl', 'director_file': 'state/runtime.json',
                       'director_node_id': 'node-a2'}}
        self.core = plan(self.source, ['main', 'alt'], 'alt')
        self.plan = apply_policy(self.core, self.policy, self.legacy)
        result = install(self.plan, self.fixture.base/'online/policy-fixture')
        self.config = result['config_path']
        self.repo = Repository(connect(self.config))

    def tearDown(self):
        self.repo.close()
        self.fixture.tearDown()

    def test_topic_reuse_fact_actions_and_sibling_visibility(self):
        topics = self.repo.records('object', {'object_type': 'world_fact'})
        self.assertEqual([o['object_id'] for o in topics], ['world_fact_employment'])
        before = project(self.repo.source_records('node-a1'))['world_fact']
        after = project(self.repo.source_records('node-a2'))['world_fact']
        alt = project(self.repo.source_records('node-b1'))['world_fact']
        self.assertEqual([r['event']['content']['text'] for r in before], ['OLD_TASK'])
        self.assertEqual([r['event']['content']['text'] for r in after], ['NEW_TASK'])
        self.assertEqual([r['event']['content']['text'] for r in alt], ['OTHER_BRANCH_TASK'])
        self.assertEqual({r['event']['event_id'] for r in self.core['events']},
                         {r['event']['event_id'] for r in self.plan['events']} - {
                         r['event']['event_id'] for r in self.plan['events']
                         if r['event']['event_type'] == 'director_state' and r['node_id'] == 'node-a2'})

    def test_original_commit_time_and_final_snapshot_use_real_sources(self):
        from script.compat.file_story.inventory import stable
        from script.workflow.pipeline.management import branch_state
        for node, commit in zip(('node-a1', 'node-a2', 'node-b1'), self.commits):
            event = self.repo.require('event', stable('fixture', 'nodes/'+node+'/meta.json', ''))
            self.assertNotIn('created_at', event['content'])
            self.assertEqual(event['content']['committed_at'], commit['committed_at'])
        end = [r for r in self.repo.source_records('node-a2') if r['event']['event_type'] == 'director_state']
        self.assertEqual(unpack(end[-1]['event']['content'])[0]['last_progress'], 'FINAL_DIRECTOR_STATE')
        self.assertFalse([r for r in self.repo.source_records('node-a1') if r['event']['event_type'] == 'director_state'])
        self.assertFalse([r for r in self.repo.source_records('node-b1') if r['event']['event_type'] == 'director_state'])
        self.assertEqual(branch_state(self.repo, 'main'), 'open')
        result = verify(self.plan, self.config, check_opening=False)
        self.assertTrue(result['ok'])
        self.assertEqual(result['opening_checks'], [])

    def test_old_rule_is_historical_note_without_losing_source_text(self):
        note = next(row for row in self.repo.source_records('node-a1')
                    if row['event']['type_name'] == 'old-rule')
        self.assertEqual(note['event']['event_type'], 'author_notes')
        self.assertEqual(note['object_id'], 'author_notes_story')
        value, _ = unpack(note['event']['content'])
        self.assertTrue(value['historical_only'])
        self.assertEqual(value['text'], 'HISTORICAL_CREATIVE_NOTE')
        self.assertFalse([r for r in project(self.repo.source_records('node-a1'))['world_fact']
                          if r['event']['content']['id'] == 'old-rule'])
