"""Normal two-level compaction, scoped repairs and real batch CLI use."""
from copy import deepcopy
from dataclasses import replace
import json
import shutil
import subprocess
import sys
from common import REPO
from creative_common import CreativeCase
from script.cli.main import execute


class Capsule(CreativeCase):
    def setUp(self):
        super().setUp()
        settings=deepcopy(self.app.resources.settings)
        settings['creative']['capsule_mode']=True
        settings['creative']['capsule']['defaults']['level_1_events']=2
        settings['creative']['capsule']['defaults']['level_2_capsules']=2
        self.app.resources=replace(self.app.resources,settings=settings)

    def memory(self,node,text,key='player',**options):
        return self.call('business.save',node_id=node,kind='role_memory',key=key,
            content={'character_id':key,'claim':text},**options)['event']

    def check(self,node,objects=None):
        params={'node_id':node,'view':'full'}
        if objects is not None:params['object_ids']=objects
        return self.call('capsule.check',**params)

    def save_batches(self,node,checks,level):
        entries=[]
        for obj in checks['objects']:
            for batch in obj['level_'+str(level)]['batches']:
                entries.append({'object_id':obj['object_id'],'level':level,
                    'source_event_ids':batch['source_event_ids'],
                    'supersedes_capsule_event_ids':batch['supersedes_capsule_event_ids'],
                    'content':{'summary':'TEST_OVERVIEW '+obj['object_id'] if batch['source_event_ids'] else '',
                               'literary_details':{'承诺':'TEST_PROMISE'}}})
        return self.call('capsule.save',node_id=node,content={'capsules':entries}),entries

    def finish_source(self,node):
        self.director(node);self.call('author.save',node_id=node,content={'literary_text':'TEST_PUBLISHED_PROSE'})
        self.finish(node)

    def test_default_thresholds_two_levels_and_independent_exact_recall(self):
        cfg=self.app.resources.settings['creative']
        cfg['capsule']['defaults'].update(level_1_events=10,level_2_capsules=5)
        cfg['recall'].update(memory_recent=1,memory_related=0)
        self.root_node();node=self.open()['node_id']
        records=[self.memory(node,'TEST_MEMORY_'+str(index)) for index in range(67)]
        checks=self.check(node,['role_memory_player'])
        self.assertEqual(checks['objects'][0]['level_1']['pending_count'],67)
        self.assertEqual(len(checks['objects'][0]['level_1']['batches']),6)
        first,_=self.save_batches(node,checks,1)
        second_checks=self.check(node,['role_memory_player'])
        self.assertEqual(second_checks['objects'][0]['level_1']['pending_count'],7)
        self.assertEqual(second_checks['objects'][0]['level_2']['pending_count'],6)
        second,_=self.save_batches(node,second_checks,2)
        self.finish_source(node);next_node=self.open()['node_id']
        recalled=self.call('scene.context',node_id=next_node)
        self.assertTrue(recalled['capsule_mode'])
        self.assertEqual(recalled['memory_counts']['player'],{'total':67,'selected':1})
        exact=recalled['projection']['role_memory']
        self.assertEqual([row['event']['event_id'] for row in exact],[records[-1]['event_id']])
        self.assertEqual({row['event']['event_id'] for row in recalled['capsules']},
                         {second['capsules'][0]['event_id'],first['capsules'][-1]['event_id']})
        self.assertEqual(sum(row['covered_event_count'] for row in recalled['capsules']),60)
        original=self.call('context.read',node_id=next_node,event_ids=[records[0]['event_id']])
        self.assertEqual(original['sources'][0]['event']['content']['payload']['claim'],'TEST_MEMORY_0')
        packet=self.director(next_node,capsule_event_ids=[row['event']['event_id'] for row in recalled['capsules']],
                             capsule_object_ids=recalled['capsule_object_ids'])
        expanded=self.call('director.read',node_id=next_node,packet_event_id=packet['packet_event_id'])
        self.assertEqual(len(expanded['sources']),2)
        self.assertTrue(all(row['event']['event_action']=='summarize' for row in expanded['sources']))
        self.assertEqual(self.call('record.list',entity='relation',filters={'relation_type':'creative_source'})['total'],0)

    def test_batch_categories_policy_and_budget(self):
        self.app.resources.settings['creative']['capsule']['kinds']['world_fact']={'level_1_events':3}
        self.app.resources.settings['creative']['capsule']['max_batches_per_check']=2
        self.root_node();node=self.open()['node_id']
        for index in range(5):self.memory(node,'PLAYER_'+str(index))
        for index in range(3):self.call('business.save',node_id=node,kind='world_fact',key='history',content={'id':'history','text':'FACT_'+str(index)})
        checks=self.check(node,['role_memory_player','world_fact_history'])
        self.assertEqual(len(checks['objects']),2)
        self.assertEqual([len(obj['level_1']['batches']) for obj in checks['objects']],[1,1])
        self.assertEqual(checks['objects'][0]['level_1']['deferred_batch_count'],1)
        self.assertEqual(checks['objects'][1]['policy']['level_1_events'],3)
        self.save_batches(node,checks,1)
        remaining=self.check(node,['role_memory_player','world_fact_history'])
        self.assertEqual(remaining['objects'][0]['level_1']['pending_count'],3)
        self.assertEqual(remaining['objects'][1]['level_1']['pending_count'],0)

    def test_branch_local_repair_supersession_and_parent_rebuild(self):
        self.root_node();shared=self.open()['node_id']
        originals=[self.memory(shared,'SHARED_'+str(index)) for index in range(4)]
        first,_=self.save_batches(shared,self.check(shared,['role_memory_player']),1)
        second,_=self.save_batches(shared,self.check(shared,['role_memory_player']),2)
        self.finish_source(shared)
        main=self.open()['node_id']
        self.memory(main,'MAIN_CORRECTION',event_action='replace',target_event_ids=[originals[0]['event_id']])
        self.call('branch.fork',branch_id='alternate',from_node_id=shared,node_id='alternate-draft')
        alt=self.call('scene_next',branch_id='alternate',mode='normal',content={'raw_user_messages':[{'text':'ALT','source':'simulation'}]})['node_id']
        before=self.call('capsule.read',node_id=main,object_ids=['role_memory_player'],include_history=True)['objects'][0]
        states={row['event']['event_id']:row['capsule_status'] for row in before['history']}
        self.assertEqual(states[first['capsules'][0]['event_id']],'stale')
        self.assertEqual(states[second['capsules'][0]['event_id']],'stale')
        self.assertEqual([row['event']['event_id'] for row in before['overview']],[first['capsules'][1]['event_id']])
        checks=self.check(main,['role_memory_player'])
        self.assertEqual(checks['objects'][0]['level_1']['batches'][0]['source_event_ids'],[originals[1]['event_id']])
        self.assertTrue(checks['objects'][0]['level_2']['blocked_capsule_ids'])
        repaired,_=self.save_batches(main,checks,1)
        next_checks=self.check(main,['role_memory_player'])
        self.assertEqual(next_checks['objects'][0]['level_2']['batches'][0]['supersedes_capsule_event_ids'],[second['capsules'][0]['event_id']])
        parent,_=self.save_batches(main,next_checks,2)
        main_view=self.call('capsule.read',node_id=main,object_ids=['role_memory_player'],include_history=True)['objects'][0]
        self.assertEqual([row['event']['event_id'] for row in main_view['overview']],[parent['capsules'][0]['event_id']])
        self.assertEqual(main_view['overview'][0]['covered_event_count'],3)
        alt_view=self.call('capsule.read',node_id=alt,object_ids=['role_memory_player'],include_history=True)['objects'][0]
        self.assertEqual([row['event']['event_id'] for row in alt_view['overview']],[second['capsules'][0]['event_id']])
        self.assertEqual(alt_view['overview'][0]['covered_event_count'],4)
        self.assertNotIn(repaired['capsules'][0]['event_id'],{row['event']['event_id'] for row in alt_view['history']})
        self.assertEqual(self.call('record.get',entity='event',record_id=first['capsules'][0]['event_id'])['state'],'active')

    def test_cancel_entire_batch_retires_it_without_raw_tail_fallback(self):
        self.root_node();node=self.open()['node_id']
        sources=[self.memory(node,'TO_CANCEL_'+str(index)) for index in range(2)]
        original,_=self.save_batches(node,self.check(node,['role_memory_player']),1)
        self.call('business.save',node_id=node,kind='role_memory',key='player',event_action='cancel',target_event_ids=[event['event_id'] for event in sources])
        checks=self.check(node,['role_memory_player'])
        batch=checks['objects'][0]['level_1']['batches'][0]
        self.assertEqual(batch['source_event_ids'],[])
        self.assertEqual(batch['supersedes_capsule_event_ids'],[original['capsules'][0]['event_id']])
        self.save_batches(node,checks,1)
        read=self.call('capsule.read',node_id=node,object_ids=['role_memory_player'],include_history=True)['objects'][0]
        self.assertEqual(read['overview'],[])
        self.assertFalse(self.check(node,['role_memory_player'])['objects'][0]['level_1']['needs_summary'])

    def test_batch_save_replay_preserves_content_and_only_ownership_relations(self):
        self.root_node();node=self.open()['node_id']
        for index in range(4):self.memory(node,'REPLAY_'+str(index))
        before=self.call('database.info')['counts']
        first,entries=self.save_batches(node,self.check(node,['role_memory_player']),1)
        saved=self.call('database.info')['counts']
        replay=self.call('capsule.save',node_id=node,content={'capsules':entries})
        self.assertEqual([row['event_id'] for row in first['capsules']],[row['event_id'] for row in replay['capsules']])
        self.assertTrue(all(row['already_exists'] for row in replay['capsules']))
        self.assertEqual(self.call('database.info')['counts'],saved)
        self.assertEqual(saved['object'],before['object'])
        self.assertEqual(saved['event']-before['event'],2)
        self.assertEqual(saved['relation']-before['relation'],2)
        self.assertEqual(len(self.call('business.read',node_id=node,kind='role_memory')['current']),4)
        self.finish_source(node)
        before_node=self.call('record.get',entity='node',record_id=node)
        self.call('capsule.save',node_id=node,content={'capsules':entries})
        self.assertEqual(self.call('record.get',entity='node',record_id=node),before_node)

    def test_low_level_summary_uses_same_contract_and_not_fact_projection(self):
        self.root_node();node=self.open()['node_id']
        source=self.memory(node,'EXACT')
        event=self.call('event.create',node_id=node,
            object={'object_id':'role_memory_player','object_type':'role_memory','object_key':'player','name':'player'},
            event={'event_type':'role_memory','type_name':'player','event_action':'summarize','content':{
                'summary':'LOW_LEVEL_OVERVIEW','_capsule':{'level':1,'source_event_ids':[source['event_id']],'supersedes_capsule_event_ids':[]}}})['event']
        self.assertEqual(self.call('capsule.read',node_id=node,object_ids=['role_memory_player'])['objects'][0]['overview'][0]['event']['event_id'],event['event_id'])
        self.assertEqual(len(self.call('business.read',node_id=node,kind='role_memory')['current']),1)

    def test_history_cutoff_keeps_late_summary_revision_out_of_open_scene(self):
        self.root_node();first=self.open()['node_id']
        records=[self.memory(first,'HISTORY_'+str(index)) for index in range(2)]
        original,_=self.save_batches(first,self.check(first,['role_memory_player']),1)
        self.finish_source(first);current=self.open()['node_id']
        event=self.call('node.revise',node_id=first,branch_id='main',
            object={'object_id':'role_memory_player','object_type':'role_memory','object_key':'player','name':'player'},
            event={'event_id':'late-summary','event_type':'role_memory','type_name':'player','event_action':'summarize',
                'content':{'summary':'LATE_VERSION','_capsule':{'level':1,'source_event_ids':[record['event_id'] for record in records],
                    'supersedes_capsule_event_ids':[original['capsules'][0]['event_id']]}}})['event']
        view=self.call('capsule.read',node_id=current,object_ids=['role_memory_player'],include_history=True)['objects'][0]
        self.assertEqual([row['event']['event_id'] for row in view['overview']],[original['capsules'][0]['event_id']])
        self.assertNotIn(event['event_id'],{row['event']['event_id'] for row in view['history']})
        self.finish_source(current);next_node=self.open()['node_id']
        later=self.call('capsule.read',node_id=next_node,object_ids=['role_memory_player'])['objects'][0]['overview']
        self.assertEqual([row['event']['event_id'] for row in later],['late-summary'])

    def test_auto_candidates_and_switch_off_leave_ordinary_workflows_available(self):
        self.root_node();node=self.open()['node_id']
        for index in range(2):self.memory(node,'AUTO_'+str(index))
        packet=self.director(node,capsule_object_ids=['role_memory_player'])
        auto=self.check(node)
        self.assertTrue(next(obj for obj in auto['objects'] if obj['object_id']=='role_memory_player')['level_1']['needs_summary'])
        self.save_batches(node,self.check(node,['role_memory_player']),1)
        self.app.resources.settings['creative']['capsule_mode']=False
        exact=self.call('business.read',node_id=node,kind='role_memory')
        self.assertEqual(len(exact['current']),2)
        recalled=self.call('scene.context',node_id=node)
        self.assertFalse(recalled['capsule_mode']);self.assertEqual(recalled['capsules'],[])
        before=self.call('database.info')['counts']
        disabled=execute(self.app,{'operation':'capsule.check','params':{'node_id':node,'object_ids':['role_memory_player']}})
        self.assertEqual(disabled['error']['code'],'CAPSULE_DISABLED')
        self.assertEqual(self.call('database.info')['counts'],before)

    def test_real_cli_batch_save_help_and_unicode_content(self):
        self.root_node();node=self.open()['node_id'];sources=[self.memory(node,'CLI_'+str(index)) for index in range(2)]
        conf=self.root/'script-conf';shutil.copytree(REPO/'script/conf',conf)
        path=conf/'creative.json';config=json.loads(path.read_text(encoding='utf8'));config['capsule_mode']=True
        path.write_text(json.dumps(config),encoding='utf8')
        runtime_path=conf/'runtime.json';runtime=json.loads(runtime_path.read_text(encoding='utf8'))
        runtime['logging']['default_path']=str(self.root/'cli-logs')
        runtime_path.write_text(json.dumps(runtime),encoding='utf8')
        runner=self.root/'capsule_cli.py'
        runner.write_text('import sys\nsys.path.insert(0,'+repr(str(REPO))+')\nfrom script.cli import main as cli\noriginal=cli.bootstrap\ncli.bootstrap=lambda **options: original(conf_path='+repr(str(conf))+',**options)\ncli.main()\n',encoding='utf8')
        command=[sys.executable,'-B','-X','utf8',str(runner)]
        content={'capsules':[{'object_id':'role_memory_player','level':1,'source_event_ids':[event['event_id'] for event in sources],
            'content':{'summary':'长期“记忆”\n保留  空格。','details':{'承诺':'等铃声之后'}}}]}
        result=subprocess.run(command+['capsule-save','--config',str(self.config),'--node-id',node,'--content-file','-'],
            input=json.dumps(content,ensure_ascii=False),capture_output=True,text=True,encoding='utf8',check=True)
        saved=json.loads(result.stdout);self.assertTrue(saved['ok'],saved)
        read=self.call('capsule.read',node_id=node,object_ids=['role_memory_player'])['objects'][0]['overview'][0]
        self.assertEqual(read['event']['content']['summary'],content['capsules'][0]['content']['summary'])
        help_result=subprocess.run(command+['capsule-save','--help'],capture_output=True,text=True,encoding='utf8',check=True)
        self.assertIn('supersedes_capsule_event_ids',help_result.stdout)
        self.assertIn('$OutputEncoding',help_result.stdout)
        self.assertEqual(result.stderr,'');self.assertEqual(help_result.stderr,'')
        log_path=self.root/'cli-logs'/runtime['logging']['filename']
        records=[json.loads(line) for line in log_path.read_text(encoding='utf8').splitlines()]
        completion=next(record for record in records if record['message']=='operation.completed' and record['operation']=='capsule.save')
        self.assertEqual(completion['result']['capsule_receipts'][0]['event_id'],saved['data']['capsules'][0]['event_id'])
        self.assertNotIn('summary',completion['result']['capsule_receipts'][0])


    def test_input_capsule_does_not_become_a_dialogue_turn_or_exported_input(self):
        self.app.resources.settings['creative']['capsule']['kinds']['user_input']={'enabled':True}
        self.root_node();scene=self.open('dialogue',raw='QUESTION_1');node=scene['node_id'];self.director(node)
        self.call('dialogue.save',node_id=node,turn_id=scene['raw_input_event_ids'][0],content={'literary_text':'ANSWER_1','scene_complete':False})
        second=self.call('dialogue.input',node_id=node,content={'raw_user_messages':[{'text':'QUESTION_2','source':'simulation'}]})
        self.save_batches(node,self.check(node,['user_input_workflow']),1)
        self.call('dialogue.save',node_id=node,turn_id=second['turn_id'],content={'literary_text':'ANSWER_2','scene_complete':True})
        self.assertEqual(len(self.call('dialogue.read',node_id=node)['inputs']),2)
        self.assertEqual(self.call('author.read',node_id=node)['literary_text'],'ANSWER_1\n\nANSWER_2')
        self.finish(node)
        snapshot=json.loads((self.root/'reader/story/functional/story.json').read_text(encoding='utf8'))
        exported=json.dumps(snapshot,ensure_ascii=False)
        self.assertNotIn('_capsule',exported)
        self.assertNotIn('TEST_OVERVIEW',exported)
        rewritten=self.call('node.rewrite',node_id=node,branch_id='main',
            content={'raw_user_messages':[{'text':'REWRITE','source':'simulation'}]},output_root=str(self.root/'reader'),generate=False)
        new_node=rewritten['scene']['node_id']
        events=self.call('node.events',node_id=new_node)['items']
        stored=next(event['content']['raw_user_messages'] for event in events if event['event_type']=='user_input')
        self.assertEqual([message['text'] for message in stored],['QUESTION_1','QUESTION_2','REWRITE'])
        self.assertTrue(self.call('scene.context',node_id=new_node)['capsule_mode'])


    def test_summary_revision_keeps_source_batch_order_and_level_two_count(self):
        self.root_node();node=self.open()['node_id']
        sources=[self.memory(node,'ORDER_'+str(index)) for index in range(4)]
        first,_=self.save_batches(node,self.check(node,['role_memory_player']),1)
        refined=self.call('capsule.save',node_id=node,content={'capsules':[{
            'object_id':'role_memory_player','level':1,'source_event_ids':[source['event_id'] for source in sources[:2]],
            'supersedes_capsule_event_ids':[first['capsules'][0]['event_id']], 'content':{'summary':'REFINED_OLDER_BATCH'}}]})
        overview=self.call('capsule.read',node_id=node,object_ids=['role_memory_player'])['objects'][0]['overview']
        expected=[refined['capsules'][0]['event_id'],first['capsules'][1]['event_id']]
        self.assertEqual([row['event']['event_id'] for row in overview],expected)
        check=self.check(node,['role_memory_player'])['objects'][0]['level_2']
        self.assertEqual(check['pending_count'],2)
        self.assertEqual(check['batches'][0]['source_event_ids'],expected)


    def test_jobs_view_omits_idle_and_save_returns_affected_next_jobs(self):
        self.root_node();node=self.open()['node_id']
        for i in range(4):self.memory(node,'SOURCE_'+str(i))
        self.memory(node,'IDLE','idle')
        ids=['role_memory_player','role_memory_idle']
        jobs=self.call('capsule.check',node_id=node,object_ids=ids)
        self.assertEqual([o['object_id'] for o in jobs['objects']],['role_memory_player'])
        self.assertEqual(jobs['checked_count'],2)
        self.assertEqual(jobs['idle_count'],1)
        full=self.call('capsule.check',node_id=node,object_ids=ids,view='full')
        self.assertEqual(jobs['objects'],[o for o in full['objects'] if o['object_id']=='role_memory_player'])
        receipt,entries=self.save_batches(node,jobs,1)
        self.assertEqual(receipt['next_jobs']['checked_count'],1)
        self.assertTrue(receipt['next_jobs']['objects'][0]['level_2']['batches'])
        again=self.call('capsule.save',node_id=node,content={'capsules':entries},include_next_jobs=False)
        self.assertNotIn('next_jobs',again)
        self.assertTrue(all(r['already_exists'] for r in again['capsules']))
