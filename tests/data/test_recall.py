"""Recall tuning, exact scoped supplements and the v5 sample adapter."""
import json
import unittest
from copy import deepcopy
from dataclasses import replace
import shutil
from common import REPO
from creative_common import CreativeCase
from script.cli.bootstrap import bootstrap
from script.workflow.cli.api import Application
from script.cli.main import execute


def open_sample_history(case):
    """Read a copied sample's completed prefix independently of its mutable draft head."""
    from uuid import uuid4
    head=case.call('branch.read',branch_id='main')['head']['node_id']
    path=case.app.repository.ancestor_path(head)
    nodes={node['node_id']:node for node in case.app.repository.records('node',{'node_id':path})}
    history=[node for node in path if nodes[node]['node_type']!='root' and nodes[node]['state']=='active']
    case.assertTrue(history)
    branch='sample-reading-'+uuid4().hex
    case.call('branch.fork',branch_id=branch,from_node_id=history[-1],node_id='draft-'+branch)
    scene=case.call('scene_next',branch_id=branch,mode='normal',
                   content={'raw_user_messages':[{'text':'TEST_SAMPLE_RECALL','source':'simulation'}]})
    return scene,history


class Recall(CreativeCase):
    def tune(self, **values):
        settings = deepcopy(self.app.resources.settings)
        settings['creative']['recall'].update(values)
        self.app.resources = replace(self.app.resources, settings=settings)

    def test_relationship_selection_keeps_global_recent_six_then_explicit_sources(self):
        self.root_node(); node = self.open()['node_id']
        ids = []
        for index in range(10):
            ids.append(self.call('business.save', node_id=node, kind='relationship',
                key='player:one' if index % 2 == 0 else 'player:two',
                content={'id':'PAIR', 'character_ids':['player','one' if index % 2 == 0 else 'two'],
                         'text':'RELATION_' + str(index)})['event']['event_id'])
        self.call('business.save', node_id=node, kind='relationship', key='other:third',
                  content={'id':'OTHER_PAIR', 'character_ids':['other','third'], 'text':'UNRELATED'})
        self.director(node); self.call('author.save', node_id=node, content={'literary_text':'TEST_PREVIOUS'})
        self.finish(node); next_node = self.open()['node_id']
        result = self.call('scene.context',view='full', node_id=next_node)
        relationships = result['projection']['relationship']
        self.assertEqual([row['event']['event_id'] for row in relationships], ids[-6:])
        evidence = result['selection_diagnostics']['categories']['relationship']
        self.assertEqual((evidence['available_count'], evidence['candidate_count'], evidence['automatic_count']), (11,10,6))
        self.assertEqual(evidence['limits'], {'total':6})
        self.assertEqual(evidence['automatic_boundary']['first']['event_id'], ids[-6])
        self.assertEqual(evidence['automatic_boundary']['last']['event_id'], ids[-1])
        pinned = self.call('scene.context',view='full', node_id=next_node, event_ids=[ids[0]])
        self.assertEqual({row['event']['event_id'] for row in pinned['projection']['relationship']}, set(ids[-6:]+[ids[0]]))
        pin_evidence = pinned['selection_diagnostics']['categories']['relationship']
        self.assertEqual((pin_evidence['automatic_count'], pin_evidence['explicit_count'], pin_evidence['selected_count']), (6,1,7))
        self.tune(relationship_limit=2)
        limited = self.call('scene.context',view='full', node_id=next_node)
        self.assertEqual([r['event']['event_id'] for r in limited['projection']['relationship']], ids[-2:])
        self.tune(relationship_limit=0)
        self.assertEqual(self.call('scene.context',view='full', node_id=next_node)['projection']['relationship'], [])
        self.call('branch.fork', branch_id='alternate', from_node_id='root', node_id='alternate-draft')
        alt = self.call('scene_next', branch_id='alternate', content={'raw_user_messages':[{'text':'ALT','source':'simulation'}]})['node_id']
        self.tune(relationship_limit=6)
        self.assertEqual(self.call('scene.context',view='full', node_id=alt)['projection']['relationship'], [])

    def test_relationship_replace_and_cancel_are_applied_before_recent_limit(self):
        self.root_node(); node = self.open()['node_id']
        originals = []
        for index in range(8):
            originals.append(self.call('business.save', node_id=node, kind='relationship', key='player:one',
                content={'id':'PAIR','character_ids':['player','one'],'text':'RELATION_' + str(index)})['event']['event_id'])
        replacement = self.call('business.save', node_id=node, kind='relationship', key='player:one',
            content={'id':'PAIR','character_ids':['player','one'],'text':'CORRECTION'},
            event_action='replace', target_event_ids=[originals[0]])['event']['event_id']
        self.call('business.save', node_id=node, kind='relationship', key='player:one',
                  event_action='cancel', target_event_ids=[originals[-1]])
        self.director(node); self.call('author.save', node_id=node, content={'literary_text':'TEST_PREVIOUS'})
        self.finish(node); next_node = self.open()['node_id']
        result = self.call('scene.context',view='full', node_id=next_node)
        self.assertEqual([r['event']['event_id'] for r in result['projection']['relationship']], originals[2:-1]+[replacement])
        self.assertEqual(result['selection_diagnostics']['categories']['relationship']['candidate_count'], 7)

    def test_profile_incremental_events_recent_related_capsules_and_original_lookup(self):
        self.tune(profile_recent=2, profile_related=1)
        self.root_node(); node = self.open()['node_id']
        settings = deepcopy(self.app.resources.settings)
        settings['creative']['capsule_mode'] = True
        self.app.resources = replace(self.app.resources, settings=settings)
        ids = []
        for index in range(12):
            content = {'character_id':'player', 'name':'TEST_NAME',
                       'facets':{'change':'远处回声' if index == 0 else 'CHANGE_' + str(index)}}
            ids.append(self.call('business.save', node_id=node, kind='role_profile', key='player',
                                 content=content)['event']['event_id'])
        self.call('business.save', node_id=node, kind='role_profile', key='other',
                  content={'character_id':'other','name':'OTHER_NAME','facets':{'change':'UNSELECTED'}})
        check = self.call('capsule.check', node_id=node, object_ids=['role_profile_player'])
        obj = check['objects'][0]
        self.assertTrue(obj['enabled'])
        self.assertEqual(obj['level_1']['batches'][0]['source_event_ids'], ids[:10])
        saved = self.call('capsule.save', node_id=node, content={'capsules':[{
            'object_id':'role_profile_player','level':1,'source_event_ids':ids[:10],
            'content':{'summary':'TEST_LONG_TERM_SIDE_PORTRAIT','自由侧面':{'来源':'INITIAL_CHANGE'}}}]})
        self.director(node); self.call('author.save', node_id=node, content={'literary_text':'TEST_PREVIOUS'})
        self.finish(node); next_node = self.open(raw='远处回声')['node_id']
        result = self.call('scene.context',view='full', node_id=next_node)
        self.assertEqual([r['event']['event_id'] for r in result['projection']['role_profile']], ids[-2:]+[ids[0]])
        self.assertEqual(result['selection_diagnostics']['categories']['role_profile']['character_counts']['player'],
                         {'total':12,'selected':3,'recent':2,'related':1})
        self.assertIn('role_profile_player', result['capsule_object_ids'])
        self.assertEqual([r['event']['event_id'] for r in result['capsules']], [saved['capsules'][0]['event_id']])
        exact = self.call('context.read', node_id=next_node, event_ids=[ids[4]])
        self.assertEqual(exact['sources'][0]['event']['content']['payload']['facets'], {'change':'CHANGE_4'})
        self.assertEqual(result['projection']['role_profile'][-2]['event']['content']['facets'], {'change':'CHANGE_11'})
        # Long-term summary activation is independent of an exact-recency budget.
        self.tune(profile_recent=0, profile_related=0)
        summary_only = self.call('scene.context',view='full', node_id=next_node)
        self.assertEqual(summary_only['projection']['role_profile'], [])
        self.assertIn('role_profile_player', summary_only['capsule_object_ids'])
        self.assertEqual(len(summary_only['capsules']), 1)
        settings = deepcopy(self.app.resources.settings)
        settings['creative']['capsule_mode'] = False
        self.app.resources = replace(self.app.resources, settings=settings)
        self.tune(profile_recent=2, profile_related=0)
        exact_only = self.call('scene.context',view='full', node_id=next_node)
        self.assertEqual(len(exact_only['projection']['role_profile']), 2)
        self.assertEqual(exact_only['capsules'], [])

    def test_selection_diagnostics_logs_counts_boundaries_and_zero_score_without_prose(self):
        self.root_node(); node = self.open()['node_id']
        for index in range(4):
            self.call('business.save', node_id=node, kind='world_fact', key='FACT_' + str(index),
                      content={'id':'FACT_' + str(index),'text':'山海' if index == 0 else '甲乙丙丁'})
        self.director(node); self.call('author.save', node_id=node, content={'literary_text':'无关文字'})
        self.finish(node); next_node = self.open(raw='山海')['node_id']
        self.tune(world_fact_limit=3)
        result = self.call('scene.context',view='full', node_id=next_node, character_ids=['player'])
        evidence = result['selection_diagnostics']['categories']['world_fact']
        self.assertEqual((evidence['candidate_count'], evidence['automatic_count'], evidence['positive_match_count'],
                          evidence['zero_score_selected_count']), (4,3,1,2))
        self.assertEqual(evidence['selected_score_range'], [0,1])
        records = [json.loads(line) for line in (self.app.logger.default_path/'runtime.log').read_text(encoding='utf-8').splitlines()]
        done = next(row for row in reversed(records) if row['message']=='operation.completed' and row['operation']=='scene.context')
        self.assertEqual(done['result']['selection_diagnostics'], result['selection_diagnostics'])
        self.assertEqual(done['result']['selected_character_ids'], ['player'])
        started = next(row for row in reversed(records) if row['message']=='operation.started' and row['operation']=='scene.context')
        self.assertEqual(started['params']['character_ids'], ['player'])
        self.assertNotIn('甲乙丙丁', json.dumps(done, ensure_ascii=False))
        # Diagnostics use data already fetched by recall, not extra per-event SQL.
        from unittest.mock import patch
        from script.workflow.pipeline.creative import recall
        statements = []; self.app.repository._store.db.set_trace_callback(statements.append)
        try:
            self.call('scene.context',view='full', node_id=next_node)
            observed = len([s for s in statements if s.lstrip().upper().startswith(('SELECT','WITH'))])
            statements.clear()
            with patch.object(recall, 'complete_diagnostics', return_value=result['selection_diagnostics']):
                self.call('scene.context',view='full', node_id=next_node)
            without = len([s for s in statements if s.lstrip().upper().startswith(('SELECT','WITH'))])
            self.assertEqual(observed, without)
        finally:
            self.app.repository._store.db.set_trace_callback(None)
        from contextlib import redirect_stdout
        import io
        from script.cli.arguments import parse_request
        output = io.StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit):parse_request(['scene-context','--help'], self.app.resources)
        for marker in ('selection_diagnostics','profile_recent','relationship_limit','默认6'):
            self.assertIn(marker, output.getvalue())

    def test_capsule_switch_enables_overview_without_blocking_scene_context(self):
        self.root_node();node=self.open()['node_id']
        conf=self.root/'capsule-conf';shutil.copytree(REPO/'script/conf',conf)
        file=conf/'creative.json';value=json.loads(file.read_text(encoding='utf8'));value['capsule_mode']=True
        file.write_text(json.dumps(value),encoding='utf8')
        resources=bootstrap(conf,self.app.resources.project_root)
        app=Application(self.config,resources=resources)
        try:
            result=execute(app,{'operation':'scene.context','params':{'node_id':node}})
            self.assertTrue(result['ok'],result)
            self.assertTrue(result['data']['capsule_mode'])
            self.assertEqual(result['data']['capsules'],[])
        finally:app.close();bootstrap()

    def test_configured_recent_related_and_pinned_memory(self):
        self.root_node()
        node=self.open()['node_id']
        self.call('business.save',node_id=node,kind='role_profile',key='player',content={'character_id':'player','name':'TEST_NAME','is_protagonist':True})
        ids=[]
        for index in range(16):
            ids.append(self.call('business.save',node_id=node,kind='role_memory',key='player',content={'character_id':'player','claim':'TEST_OLD_MATCH' if index==0 else 'TEST_MEMORY_'+str(index)})['event']['event_id'])
        self.director(node);self.call('author.save',node_id=node,content={'literary_text':'TEST_PREVIOUS'});self.finish(node)
        next_node=self.open(raw='TEST_OLD_MATCH')['node_id']
        conf=self.root/'conf';shutil.copytree(REPO/'script/conf',conf)
        filename=conf/'creative.json';value=json.loads(filename.read_text(encoding='utf8'))
        value['recall']['memory_recent']=2;value['recall']['memory_related']=1
        filename.write_text(json.dumps(value),encoding='utf8')
        resources=bootstrap(conf,self.app.resources.project_root)
        old_app=self.app;self.app=Application(self.config,resources=resources)
        try:
            recalled=self.call('scene.context',view='full',node_id=next_node)
            memories=[row for row in recalled['sources'] if row['event']['event_type']=='role_memory']
            self.assertEqual(len(memories),3)
            self.assertIn(ids[0],{row['event']['event_id'] for row in memories})
            pinned=self.call('scene.context',view='full',node_id=next_node,event_ids=[ids[2]])
            self.assertIn(ids[2],{row['event']['event_id'] for row in pinned['sources']})
            self.assertEqual(len(recalled['projection']['role_memory']),3)
            read=self.call('context.read',node_id=next_node,object_ids=['role_memory_player'],keyword='TEST_OLD_MATCH')
            self.assertEqual(read['sources'][0]['event']['event_id'],ids[0])
        finally:
            self.app.close();self.app=old_app;bootstrap()

    def test_two_branches_share_ancestors_without_sharing_later_events(self):
        self.root_node()
        first=self.ordinary(events=[{'kind':'role_memory','key':'player','content':{'character_id':'player','claim':'TEST_MAIN_ONLY'}}])
        fork=self.call('branch.fork',branch_id='alternate',from_node_id='root',node_id='alternate-draft')
        opened=self.call('scene_next',branch_id='alternate',mode='normal',content={'raw_user_messages':[{'text':'TEST_ALTERNATE','source':'simulation'}]})
        recalled=self.call('scene.context',view='full',node_id=opened['node_id'])
        self.assertNotIn('TEST_MAIN_ONLY',json.dumps(recalled))
        self.assertEqual(recalled['scope']['history_node_id'],'root')

    @unittest.skipUnless((REPO/'story-data/debug/optional-local-sample/sqlite.json').is_file(),
                         'Optional private story sample is not included in the public repository')
    def test_between_bell_sample_copy_recall(self):
        source=REPO/'story-data/debug/optional-local-sample'
        copy=self.root/'sample';copy.mkdir()
        cfg=json.loads((source/'sqlite.json').read_text(encoding='utf8'))
        location=source/cfg['location'];shutil.copyfile(location,copy/'sample.sqlite3')
        cfg['location']='sample.sqlite3';(copy/'sqlite.json').write_text(json.dumps(cfg),encoding='utf8')
        original=self.app;self.app=Application(copy/'sqlite.json')
        try:
            scene,_=open_sample_history(self)
            recalled=self.call('scene.context',view='full',node_id=scene['node_id'])
            self.assertTrue(recalled['previous_scene_prose'])
            self.assertTrue(recalled['projection']['role_memory'])
            memory=self.call('business.read',node_id=scene['node_id'],kind='role_memory',key='player')
            self.assertTrue(memory['current'])
            self.assertEqual(recalled['capsule_mode'], self.app.resources.settings['creative']['capsule_mode'])
        finally:self.app.close();self.app=original


class ProseReading(CreativeCase):
    def prepare_prose(self):
        self.root_node()
        self.prose_by_node = {}
        parent = 'root'
        for index in range(5):
            node = 'read-page-' + str(index)
            text = ('TEST_' + str(index) + ' 中文标点，空格  与换行。\n\n') * (index + 3)
            self.call('node.begin', node_id=node, predecessor_id=parent, branch_id='main')
            self.call('event.create', node_id=node, select_as='narrative',
                      object={'object_id':'test-prose','object_type':'narrative','object_key':'test-prose','name':'TEST_OBJECT'},
                      event={'event_id':'test-prose-'+node,'event_type':'narrative','type_name':node,
                             'content':{'literary_text':text}})
            self.call('event.create', node_id=node, select_as='summary',
                      object={'object_id':'test-summary','object_type':'scene_summary','object_key':'test-summary','name':'TEST_OBJECT'},
                      event={'event_id':'test-summary-'+node,'event_type':'scene_summary','type_name':node,
                             'content':{'summary':'TEST_SUMMARY'}})
            self.call('node.publish', node_id=node)
            self.prose_by_node[node] = text
            parent = node
        self.scene_node = self.open()['node_id']

    def pages(self, nodes, maximum):
        params={'node_id':self.scene_node,'view':'prose','source_node_ids':nodes,'max_text_chars':maximum}
        pages=[]
        while True:
            page=self.call('context.read',**params);pages.append(page)
            if page['page']['complete']:return pages
            params={'node_id':self.scene_node,'view':'prose','cursor':page['page']['next_cursor'],
                    'max_text_chars':maximum}

    def test_multiple_prose_pages_reconstruct_all_selected_text_without_duplicate_sources(self):
        self.prepare_prose()
        wanted=list(self.prose_by_node)
        before=self.call('database.info')['counts']
        pages=self.pages(wanted,150)
        self.assertGreater(len(pages),1)
        restored={node:'' for node in wanted}
        for page in pages:
            self.assertEqual(page['sources'],[])
            self.assertEqual(page['view'],'prose')
            self.assertLessEqual(page['page']['returned_characters'],150)
            self.assertEqual(page['page']['returned_characters'],
                             sum(len(n['literary_text']) for n in page['narratives']))
            for item in page['narratives']:
                self.assertEqual(item['text_start'],len(restored[item['node_id']]))
                restored[item['node_id']]+=item['literary_text']
                self.assertEqual(item['text_end'],len(restored[item['node_id']]))
        self.assertEqual(restored,self.prose_by_node)
        self.assertIsNone(pages[-1]['page']['next_cursor'])
        self.assertEqual(self.call('database.info')['counts'],before)

    def test_configured_page_budget_drives_default_and_help_preserves_open_content(self):
        self.prepare_prose()
        conf=self.root/'reading-conf';shutil.copytree(REPO/'script/conf',conf)
        file=conf/'creative.json';value=json.loads(file.read_text(encoding='utf8'))
        value['reading']['prose_page_characters']=80
        file.write_text(json.dumps(value),encoding='utf8')
        resources=bootstrap(conf,self.app.resources.project_root)
        original=self.app;self.app=Application(self.config,resources=resources)
        try:
            page=self.call('context.read',node_id=self.scene_node,view='prose',
                           source_node_ids=list(self.prose_by_node))
            self.assertEqual(page['page']['max_text_chars'],80)
            self.assertLessEqual(page['page']['returned_characters'],80)
            from script.cli.arguments import parse_request
            from contextlib import redirect_stdout
            import io
            output=io.StringIO()
            with redirect_stdout(output):
                with self.assertRaises(SystemExit):
                    parse_request(['context-read','--help'],resources)
            for text in ('--view','--cursor','--max-text-chars','next_cursor','prose_page_characters'):
                self.assertIn(text,output.getvalue())
            request,_,_,_,_=parse_request(['context-read','--config',str(self.config),
                '--node-id',self.scene_node,'--view','prose','--cursor',page['page']['next_cursor']],resources)
            result=execute(self.app,request)
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['data']['page']['max_text_chars'],80)
        finally:
            self.app.close();self.app=original;bootstrap()

    def test_cursor_keeps_selected_adopted_prose_version_and_dialogue_expands_once(self):
        self.prepare_prose()
        node=self.scene_node
        original='TEST_OLD_VERSION 中文\n\n'*15
        def select(event_id,text):
            return self.call('node.revise',node_id=node,branch_id='main',select_as='narrative',
                object={'object_id':'test-draft-prose','object_type':'narrative','object_key':'test-draft-prose','name':'TEST_OBJECT'},
                event={'event_id':event_id,'event_type':'narrative','type_name':'draft','content':{'literary_text':text}})
        self.director(node)
        saved=self.call('author.save',node_id=node,content={'literary_text':original})
        self.finish(node)
        original_id=saved['narrative_event_id']
        first=self.call('context.read',node_id=node,view='prose',source_node_ids=[node],max_text_chars=70)
        select('draft-new','TEST_NEW_VERSION')
        text=first['narratives'][0]['literary_text'];page=first
        while not page['page']['complete']:
            page=self.call('context.read',node_id=node,view='prose',
                           cursor=page['page']['next_cursor'],max_text_chars=70)
            self.assertEqual(page['narratives'][0]['narrative_event_id'],original_id)
            text+=page['narratives'][0]['literary_text']
        self.assertEqual(text,original)
        self.assertEqual(self.call('context.read',node_id=node,view='prose',
                         source_node_ids=[node])['narratives'][0]['literary_text'],'TEST_NEW_VERSION')
        opened=self.open(mode='dialogue');dialogue=opened['node_id'];self.director(dialogue)
        turn=opened['raw_input_event_ids'][0]
        self.call('dialogue.save',node_id=dialogue,turn_id=turn,
                  content={'literary_text':'TEST_FRAGMENT','scene_complete':True,'feedback':{}})
        self.finish(dialogue)
        next_node=self.open()['node_id']
        read=self.call('context.read',node_id=next_node,view='prose',source_node_ids=[dialogue])
        self.assertEqual(read['narratives'][0]['literary_text'],'TEST_FRAGMENT')
        self.assertEqual(read['sources'],[])

    def test_prose_read_stays_in_branch_and_batches_node_and_source_queries(self):
        self.prepare_prose()
        fork=self.call('branch.fork',branch_id='alternate',from_node_id='root',node_id='alternate-page')
        # The unfinished main node still has its frozen five-node history.
        db=self.app.repository._store.db
        counts=[]
        for selected in ([list(self.prose_by_node)[0]],list(self.prose_by_node)):
            statements=[];db.set_trace_callback(statements.append)
            try:
                result=self.call('context.read',node_id=self.scene_node,view='prose',
                                 source_node_ids=selected,max_text_chars=5000)
            finally:db.set_trace_callback(None)
            self.assertEqual([item['node_id'] for item in result['narratives']],selected)
            counts.append(len([s for s in statements if s.lstrip().upper().startswith(('SELECT','WITH'))]))
        self.assertEqual(counts[0],counts[1])
        alternate=self.call('scene_next',branch_id='alternate',content={
            'raw_user_messages':[{'text':'TEST_BRANCH','source':'simulation'}]})['node_id']
        root=self.call('context.read',node_id=alternate,view='prose',source_node_ids=['root'])
        self.assertEqual(root['narratives'][0]['literary_text'],'')
        self.assertEqual(root['scope']['branch_id'],'alternate')

    def test_cli_logs_targets_page_size_and_serialized_response_without_agent_log_fields(self):
        self.prepare_prose()
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from script.cli.main import main
        import io
        output=io.StringIO()
        with patch('script.cli.main.bootstrap',return_value=self.app.resources),redirect_stdout(output):
            code=main(['context-read','--config',str(self.config),'--node-id',self.scene_node,
                       '--view','prose','--source-node-ids',*self.prose_by_node,'--max-text-chars','150'])
        self.assertEqual(code,0)
        wire=output.getvalue().rstrip('\n')
        response=json.loads(wire)
        self.assertTrue(response['ok'])
        records=[json.loads(line) for line in (self.app.logger.default_path/'runtime.log').read_text(encoding='utf8').splitlines()]
        emitted=next(r for r in reversed(records) if r['message']=='response.serialized')
        invocation=emitted['invocation_id']
        pairs=[r for r in records if r.get('invocation_id')==invocation]
        start=next(r for r in pairs if r['message']=='operation.started')
        done=next(r for r in pairs if r['message']=='operation.completed')
        self.assertEqual(start['params']['source_node_ids'],list(self.prose_by_node))
        self.assertEqual(done['branch_id'],'main')
        self.assertEqual(done['database_id'],'functional')
        self.assertEqual(done['result']['narrative_characters'],response['data']['page']['returned_characters'])
        self.assertEqual(done['result']['scope']['history_node_id'],list(self.prose_by_node)[-1])
        self.assertEqual(emitted['branch_id'],'main')
        self.assertEqual(emitted['response_characters'],len(wire))
        self.assertEqual(emitted['response_utf8_bytes'],len(wire.encode('utf-8')))
        for item in response['data']['narratives']:
            self.assertNotIn(item['literary_text'],json.dumps(pairs,ensure_ascii=False))

    @unittest.skipUnless((REPO/'story-data/debug/optional-local-sample/sqlite.json').is_file(),
                         'Optional private story sample is not included in the public repository')
    def test_between_bell_copy_prose_pages_preserve_real_normal_and_dialogue_text(self):
        import sqlite3
        source=REPO/'story-data/debug/optional-local-sample'
        cfg=json.loads((source/'sqlite.json').read_text(encoding='utf8'))
        target=self.root/'sample-reading';target.mkdir()
        from contextlib import closing
        with closing(sqlite3.connect((source/cfg['location']).resolve().as_uri()+'?mode=ro',uri=True)) as original_db:
            with closing(sqlite3.connect(target/'sample.sqlite3')) as copied:
                original_db.backup(copied)
        cfg['location']='sample.sqlite3'
        config=target/'sqlite.json';config.write_text(json.dumps(cfg),encoding='utf8')
        original=self.app;self.app=Application(config,resources=original.resources)
        try:
            scene,history=open_sample_history(self)
            selected=history[-5:]
            self.scene_node=scene['node_id']
            full=self.call('context.read',node_id=self.scene_node,source_node_ids=selected,limit=1)
            expected={item['node_id']:item['literary_text'] for item in full['narratives']}
            pages=self.pages(selected,5000)
            restored={node:'' for node in selected}
            for page in pages:
                self.assertEqual(page['sources'],[])
                for item in page['narratives']:
                    restored[item['node_id']]+=item['literary_text']
            self.assertEqual(restored,expected)
            self.assertTrue(pages[-1]['page']['complete'])
        finally:
            self.app.close();self.app=original


    def test_compact_default_preserves_projection_without_source_copy(self):
        self.root_node()
        self.ordinary(events=[{'kind':'world_fact','key':'detail','content':{'id':'detail','text':'有意义的细节'*100}}])
        node=self.open()['node_id']
        compact=self.call('scene.context',node_id=node)
        self.assertIn('projection',compact)
        self.assertNotIn('sources',compact)
        full=self.call('scene.context',node_id=node,view='full')
        self.assertIn('projection',full)
        for key in ('scope','previous_scene_prose','previous_summary','selected_character_ids','projection','memory_counts','selection_diagnostics','capsules','capsule_object_ids'):
            self.assertEqual(compact[key],full[key],key)
        self.assertLess(len(json.dumps(compact)),len(json.dumps(full)))


    def test_cli_context_file_preserves_large_unicode_response_and_emits_receipt_only(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from script.cli.main import main
        from hashlib import sha256
        import io
        self.root_node()
        payload='完整原文“引号”、空格  与换行\n'*12000+'末尾验收标记'
        self.ordinary(events=[{'kind':'world_fact','key':'large','content':{'id':'large','text':payload}}])
        node=self.open()['node_id']
        expected=self.call('scene.context',node_id=node)
        for view in ('compact','full'):
            with self.subTest(view=view):
                target=self.root/'转储 文件'/f'{view}.json'
                output=io.StringIO()
                with patch('script.cli.main.bootstrap',return_value=self.app.resources),redirect_stdout(output):
                    code=main(['scene-context','--config',str(self.config),'--node-id',node,
                               '--view',view,'--output-file',str(target)])
                self.assertEqual(code,0,output.getvalue())
                receipt=json.loads(output.getvalue())
                self.assertTrue(receipt['ok'])
                raw=target.read_bytes()
                response=json.loads(raw)
                self.assertEqual(response['operation'],'scene.context')
                self.assertTrue(response['ok'])
                if view=='compact':self.assertEqual(response['data'],expected)
                self.assertEqual(response['data']['projection']['world_fact'][0]['event']['content']['text'],payload)
                self.assertEqual('sources' in response['data'],view=='full')
                self.assertEqual(receipt['data']['output_file'],str(target.resolve()))
                self.assertEqual(receipt['data']['response_utf8_bytes'],len(raw))
                self.assertEqual(receipt['data']['response_characters'],len(raw.decode('utf8')))
                self.assertEqual(receipt['data']['sha256'],sha256(raw).hexdigest())
                self.assertLess(len(output.getvalue()),1200)
                self.assertNotIn('末尾验收标记',output.getvalue())

    def test_cli_prepare_file_and_write_failure_are_reported(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from script.cli.main import main
        import io
        self.root_node()
        content=self.root/'input.json'
        content.write_text(json.dumps({'raw_user_messages':[{'text':'继续故事','source':'simulation'}]},ensure_ascii=False),encoding='utf8')
        target=self.root/'prepare.json'
        arguments=['scene-prepare','--config',str(self.config),'--branch-id','main','--content-file',str(content),'--output-file',str(target)]
        output=io.StringIO()
        with patch('script.cli.main.bootstrap',return_value=self.app.resources),redirect_stdout(output):code=main(arguments)
        self.assertEqual(code,0,output.getvalue())
        saved=json.loads(target.read_text(encoding='utf8'))
        self.assertIn('projection',saved['data']['preparation'])
        self.assertNotIn('sources',saved['data']['preparation'])
        node=saved['data']['scene']['node_id']
        # A normal filesystem failure must not claim a complete export or damage an existing file.
        target.write_text('KEEP_EXISTING',encoding='utf8')
        output=io.StringIO()
        with patch('script.cli.main.bootstrap',return_value=self.app.resources),patch('script.cli.main.os.replace',side_effect=OSError('TEST_WRITE_FAILURE')),redirect_stdout(output):
            code=main(['scene-context','--config',str(self.config),'--node-id',node,'--output-file',str(target)])
        self.assertNotEqual(code,0)
        response=json.loads(output.getvalue())
        self.assertFalse(response['ok'])
        self.assertEqual(response['error']['code'],'OUTPUT_WRITE_FAILED')
        self.assertEqual(target.read_text(encoding='utf8'),'KEEP_EXISTING')
        self.assertEqual(list(self.root.glob('.prepare.json.*.tmp')),[])


    def test_cli_output_file_preserves_business_error_and_help_has_no_file_side_effect(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from script.cli.main import main
        import io
        self.root_node()
        target=self.root/'failed.json'
        output=io.StringIO()
        with patch('script.cli.main.bootstrap',return_value=self.app.resources),redirect_stdout(output):
            code=main(['scene-context','--config',str(self.config),'--node-id','missing-node','--output-file',str(target)])
        self.assertNotEqual(code,0)
        self.assertFalse(json.loads(output.getvalue())['ok'])
        self.assertEqual(json.loads(target.read_text(encoding='utf8')),json.loads(output.getvalue()))
        untouched=self.root/'help.json'
        output=io.StringIO()
        with patch('script.cli.main.bootstrap',return_value=self.app.resources),redirect_stdout(output):
            with self.assertRaises(SystemExit) as stopped:
                main(['scene-context','--output-file',str(untouched),'--help'])
        self.assertEqual(stopped.exception.code,0)
        self.assertIn('--output-file',output.getvalue())
        self.assertIn('文件回执data',output.getvalue())
        self.assertFalse(untouched.exists())
