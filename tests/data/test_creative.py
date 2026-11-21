"""Normal scene lifecycle, immutable packet references and recovery."""
import json
import subprocess
import sys
from pathlib import Path
from common import REPO
from creative_common import CreativeCase


class Creative(CreativeCase):

    def test_director_creative_guidance_roundtrips_open_content_and_contract_reference(self):
        self.root_node();node=self.open(raw='TEST_RAW_INPUT')['node_id']
        source=self.call('business.save',node_id=node,kind='role_memory',key='player',
                         content={'character_id':'player','claim':'TEST_HISTORY'})['event']
        creative_intent='TEST_MULTI_SCENE_INTEREST\nTEST_LOCAL_FEEDBACK_AND_UNCERTAINTY'
        candidates=['TEST_DIRECTION_A',{'conflict':'TEST_TENSION','reader_interest':'TEST_INTEREST',
                                        'custom':{'possible_consequences':['TEST_EFFECT']}}]
        content={'creative_intent':creative_intent,'plot_possibilities':candidates,
                 'scene_need':'TEST_REFERENCE','custom_interpretation':{'scope':'TEST_LOCAL'},
                 'context_event_ids':[source['event_id']],
                 'groups':[{'title':'TEST_GROUP','event_ids':[source['event_id']]}]}
        packet=self.director(node,**content)
        result=self.call('director.read',node_id=node,packet_event_id=packet['packet_event_id'])
        for key,value in content.items():
            self.assertEqual(result['brief'][key],value)
        self.assertEqual([row['event']['event_id'] for row in result['sources']],[source['event_id']])
        self.assertEqual(result['raw_user_messages'][0]['text'],'TEST_RAW_INPUT')
        guide=Path(result['author_policy'])
        self.assertFalse(guide.is_absolute())
        self.assertEqual(guide.parts[:2],('role-interaction','director-author'))
        self.assertTrue((REPO/guide).is_file())
        feedback={'decision':'TEST_INDEPENDENT_SELECTION','custom':['TEST_CHANGE']}
        reply=self.call('author.save',node_id=node,source_packet_event_id=packet['packet_event_id'],
                        content={'literary_text':'TEST_COMPLETE_PROSE','feedback':feedback})
        result=self.call('author.read',node_id=node,packet_event_id=reply['packet_event_id'])
        self.assertEqual(result['feedback'],feedback)
        self.assertEqual(result['reply']['director_packet_event_id'],packet['packet_event_id'])

    def test_complete_scene_packets_display_archive_and_retry(self):
        self.root_node()
        raw='原始“输入”\n两处  空格；错字保留。'
        scene=self.open(raw=raw);node=scene['node_id']
        self.assertEqual(scene['status'],'preparing')
        self.assertEqual(self.open(raw=raw)['node_id'],node)
        self.call('author.bind',node_id=node,session_id='test-host-session',agent_id='test-host-author')
        source=self.call('business.save',node_id=node,kind='truth',key='mystery',content={'text':'TEST_TRUTH'})['event']
        packet=self.director(node,groups=[{'title':'TEST_GROUP','note':'TEST_NOTE','event_ids':[source['event_id']]}],truth_event_ids=[source['event_id']])
        expanded=self.call('director.read',node_id=node)
        self.assertEqual(expanded['raw_user_messages'][0]['text'],raw)
        self.assertEqual(len([r for r in expanded['sources'] if r['event']['event_id']==source['event_id']]),1)
        prose='TEST_COMPLETE_PROSE\n\nTEST_END'
        self.call('author.save',node_id=node,content={'literary_text':prose,'feedback':{'修改':'TEST_CHANGE'}})
        self.assertEqual(self.call('scene.status',node_id=node)['status'],'awaiting_display')
        self.assertEqual(self.call('author.read',node_id=node)['literary_text'],prose)
        event={'kind':'role_memory','key':'player','content':{'character_id':'player','claim':'TEST_MEMORY'}}
        self.finish(node,[event])
        done=self.call('scene.archive',node_id=node,content={'events':[event]},output_root=str(self.root/'reader'))
        self.assertEqual(done['status'],'complete')
        self.assertEqual(self.call('node.read',node_id=node)['narrative'],prose)
        snapshot=json.loads((self.root/'reader/story/functional/story.json').read_text(encoding='utf8'))
        self.assertEqual(snapshot['chapters'][0]['narrative'],prose)
        self.assertFalse(snapshot['chapters'][0]['display']['pending'])
        self.assertNotIn('TEST_TRUTH',json.dumps(snapshot))
        sources=self.call('record.list',entity='event',filters={'event_type':'narrative'})
        self.assertEqual(sources['total'],1)
        self.assertEqual(self.call('record.list',entity='relation',filters={'relation_type':'creative_source'})['total'],0)
        successor=self.open()
        self.assertEqual(successor['author_binding']['agent_id'],'test-host-author')
        self.assertEqual(successor['history_node_id'],node)
        expanded=self.call('scene.context',node_id=successor['node_id'])
        self.assertEqual(expanded['previous_scene_prose'],prose)
        self.director(successor['node_id'])
        packet=self.call('director.read',node_id=successor['node_id'])
        self.assertEqual(packet['previous_scene_prose'],prose)
        read=self.call('context.read',node_id=successor['node_id'],source_node_ids=[node])
        self.assertEqual(read['narratives'][0]['literary_text'],prose)

    def test_real_cli_first_scene_and_status(self):
        self.root_node()
        data=self.root/'input.json'
        data.write_text(json.dumps({'raw_user_messages':[{'text':'TEST_CLI\n  INPUT','source':'simulation'}]}),encoding='utf8')
        command=[sys.executable,'-B','-X','utf8',str(REPO/'script/cli/main.py')]
        first=json.loads(subprocess.run(command+['scene-next','--config',str(self.config),'--content-file',str(data)],capture_output=True,text=True,encoding='utf8',check=True).stdout)
        self.assertTrue(first['ok'],first)
        status=json.loads(subprocess.run(command+['scene-status','--config',str(self.config),'--node-id',first['data']['node_id']],capture_output=True,text=True,encoding='utf8',check=True).stdout)
        self.assertEqual(status['data']['status'],'preparing')


    def test_author_cli_submission_and_director_receipt_read(self):
        self.root_node()
        scene = self.open(raw='TEST_DATABASE_HANDOFF'); node = scene['node_id']
        packet = self.director(node)
        command = [sys.executable, '-B', '-X', 'utf8', str(REPO/'script/cli/main.py')]
        content = {'literary_text':'完整作品。\n\n正文只通过数据库交接。',
                   'feedback':{'note':'作者已提交作品；导演负责业务归档。'}}

        def run(*args, content=None):
            result = subprocess.run(command+list(args), input=json.dumps(content,ensure_ascii=False) if content is not None else None,
                                    capture_output=True, text=True, encoding='utf8', check=True)
            self.assertEqual(result.stderr, '')
            response = json.loads(result.stdout)
            self.assertTrue(response['ok'],response)
            return response['data']

        receipt = run('author-reply-save','--config',str(self.config),'--node-id',node,
                      '--source-packet-event-id',packet['packet_event_id'],'--content-file','-',content=content)
        # Same successful submission is reusable after a missing host notification.
        replay = run('author-reply-save','--config',str(self.config),'--node-id',node,
                     '--source-packet-event-id',packet['packet_event_id'],'--content-file','-',content=content)
        self.assertEqual(replay,receipt)
        received = run('author-reply-read','--config',str(self.config),'--node-id',node,
                       '--packet-event-id',receipt['packet_event_id'])
        self.assertEqual(received['packet_event_id'],receipt['packet_event_id'])
        self.assertEqual(received['narrative_event_id'],receipt['narrative_event_id'])
        self.assertEqual(received['literary_text'],content['literary_text'])
        self.assertEqual(received['feedback'],content['feedback'])
        self.assertEqual(received['reply']['director_packet_event_id'],packet['packet_event_id'])
        self.assertEqual(self.call('scene.status',node_id=node)['author_reply_event_id'],receipt['packet_event_id'])
        self.assertEqual(self.call('author.read',node_id=node)['packet_event_id'],receipt['packet_event_id'])
        self.finish(node)
        self.assertEqual(self.call('record.list',entity='event',filters={'event_type':'narrative'})['total'],1)
        self.assertEqual(self.call('record.list',entity='event',filters={'event_type':'author_packet'})['total'],1)


    def test_shared_workflow_objects_preserve_scene_identity_and_leaf_cleanup(self):
        self.root_node()
        def complete(raw):
            scene=self.open('dialogue',raw=raw);node=scene['node_id'];self.director(node)
            self.call('dialogue.save',node_id=node,turn_id=scene['raw_input_event_ids'][0],content={'literary_text':'TEST_PROSE '+raw,'scene_complete':True})
            self.finish(node)
            return node
        first=complete('FIRST_INPUT')
        counts=self.call('database.info')['counts']
        second=complete('SECOND_INPUT')
        self.assertEqual(self.call('database.info')['counts']['object'],counts['object'])
        for kind in ('user_input','scene_context','director_packet','dialogue_fragment','narrative','author_packet','display_metadata','director_archive'):
            rows=self.call('record.list',entity='relation',filters={'relation_type':'event','target_object_id':kind+'_workflow'})['items']
            self.assertEqual({row['target_node_id'] for row in rows},{first,second})
            events=[self.call('record.get',entity='event',record_id=row['key_id']) for row in rows]
            self.assertEqual({event['type_name'] for event in events},{first,second})
        self.assertEqual(self.call('author.read',node_id=first)['literary_text'],'TEST_PROSE FIRST_INPUT')
        self.assertEqual(self.call('author.read',node_id=second)['literary_text'],'TEST_PROSE SECOND_INPUT')
        self.call('node.delete_leaf',node_id=second)
        self.assertEqual(self.call('node.read',node_id=first)['narrative'],'TEST_PROSE FIRST_INPUT')
        self.assertIsNotNone(self.call('record.get',entity='object',record_id='narrative_workflow'))

    def test_replay_legacy_scene_context_keeps_original_object(self):
        self.root_node()
        scene=self.open();node=scene['node_id']
        from script.workflow.pipeline.creative.common import identifier
        narrative_id=identifier('narrative',node)
        self.director(node)
        content={'literary_text':'LEGACY_PROSE'}
        self.call('event.create',node_id=node,
            object={'object_id':'narrative_'+node,'object_type':'narrative','object_key':node,'name':node},
            event={'event_id':narrative_id,'event_type':'narrative','type_name':node,'content':content},select_as='narrative')
        receipt=self.call('author.save',node_id=node,content=content)
        owners=self.call('record.list',entity='relation',filters={'relation_type':'event','key_id':narrative_id})['items']
        self.assertEqual(owners[0]['target_object_id'],'narrative_'+node)
        self.assertEqual(self.call('author.read',node_id=node,packet_event_id=receipt['packet_event_id'])['literary_text'],'LEGACY_PROSE')


    def test_shared_objects_keep_branch_inputs_and_packets_separate(self):
        self.root_node();main=self.ordinary(raw='MAIN_INPUT')
        self.call('branch.fork',branch_id='alternate',from_node_id='root',node_id='alt-draft')
        alt=self.call('scene_next',branch_id='alternate',mode='normal',content={'raw_user_messages':[{'text':'ALT_INPUT','source':'simulation'}]})['node_id']
        packet=self.director(alt)
        main_packet=self.call('director.read',node_id=main)
        alt_packet=self.call('director.read',node_id=alt,packet_event_id=packet['packet_event_id'])
        self.assertEqual([message['text'] for message in main_packet['raw_user_messages']],['MAIN_INPUT'])
        self.assertEqual([message['text'] for message in alt_packet['raw_user_messages']],['ALT_INPUT'])
        rows=self.call('context.read',node_id=alt,object_ids=['user_input_workflow'])['sources']
        self.assertEqual({row['node_id'] for row in rows},{alt})
        self.assertEqual(self.call('record.list',entity='object',filters={'object_type':'director_packet'})['total'],1)


    def test_prepare_submit_recovery_and_archive_default_sources(self):
        from unittest.mock import patch
        from script.cli.main import execute
        from script.util.errors import ContractError
        self.root_node()
        opened=self.call('scene.prepare',content={'raw_user_messages':[{'text':'原始输入','source':'simulation'}]})
        node=opened['scene']['node_id']
        self.assertEqual(opened['preparation']['view'],'compact')
        director=self.director(node)
        metadata={'summary':'摘要','location':'地点','time':'时间','participants':[]}
        params={'node_id':node,'source_packet_event_id':director['packet_event_id'],
                'content':{'literary_text':'一个权威正文','feedback':{'自由':'保留'},'display':metadata},'output_root':str(self.root/'reader')}
        with patch('script.workflow.pipeline.creative.presentation.sync',side_effect=ContractError('DISPLAY_FAILED','TEST_GENERATION_FAILURE')):
            failure=execute(self.app,{'operation':'scene.submit','params':params})
        self.assertFalse(failure['ok']);self.assertIsNone(failure['data'])
        details=failure['error']['details']
        self.assertEqual(details['completed_stage'],'author_saved')
        self.assertEqual(details['node_id'],node)
        self.assertEqual(self.call('author.read',node_id=node)['literary_text'],'一个权威正文')
        ready=self.call('scene.submit',node_id=node,author_packet_event_id=details['author_packet_event_id'],content={'display':metadata},output_root=str(self.root/'reader'))
        self.assertEqual(ready['display']['publication_status'],'published')
        source=ready['narrative_event_id']
        entries=[{'kind':'role_memory','key':'player','content':{'character_id':'player','claim':'重要经历'}},
                 {'kind':'world_fact','key':'public','content':{'id':'public','text':'事实'},'source_event_ids':[]}]
        self.call('scene.archive',node_id=node,content={'events':entries,'default_source_event_ids':[source]},output_root=str(self.root/'reader'))
        from script.workflow.pipeline.creative.common import identifier
        first=self.call('record.get',entity='event',record_id=identifier('archive',node,'0'))
        second=self.call('record.get',entity='event',record_id=identifier('archive',node,'1'))
        self.assertEqual(first['content']['source_event_ids'],[source])
        self.assertNotIn('source_event_ids',second['content'])
        explicit=[{**entry,'source_event_ids':entry.get('source_event_ids',[source])} for entry in entries]
        self.assertTrue(self.call('scene.archive',node_id=node,content={'events':explicit},output_root=str(self.root/'reader'))['published'])
        prepared=self.call('scene.prepare',node_id=node,content={'raw_user_messages':[{'text':'原始输入','source':'simulation'}]})
        self.assertIsNone(prepared['preparation'])
        self.assertEqual(prepared['scene']['status'],'complete')

    def test_prepare_failure_exposes_saved_node_and_retry_reuses_it(self):
        from script.cli.main import execute
        self.root_node()
        params={'content':{'raw_user_messages':[{'text':'继续','source':'simulation'}]},'event_ids':['missing-source']}
        failed=execute(self.app,{'operation':'scene.prepare','params':params})
        self.assertFalse(failed['ok'])
        details=failed['error']['details'];self.assertEqual(details['completed_stage'],'scene_opened')
        retried=self.call('scene.prepare',node_id=details['node_id'],content=params['content'])
        self.assertEqual(retried['scene']['node_id'],details['node_id'])
        self.assertEqual(self.call('database.info')['counts']['node'],2)

    def test_composite_submit_cannot_run_inside_batch_transaction(self):
        from script.cli.main import execute
        self.root_node();node=self.open()['node_id'];packet=self.director(node)
        params={'node_id':node,'source_packet_event_id':packet['packet_event_id'],'content':{'literary_text':'未提交','display':{'summary':'摘要','location':'地点','time':'时间','participants':[]}}}
        before=self.call('database.info')['counts']
        response=execute(self.app,{'operation':'batch','params':{'commands':[{'operation':'scene.submit','params':params}]}})
        self.assertFalse(response['ok']);self.assertEqual(response['error']['code'],'COMPOSITE_IN_BATCH')
        self.assertEqual(self.call('database.info')['counts'],before)


    def test_real_cli_composite_chain_preserves_one_publication(self):
        self.root_node()
        command=[sys.executable,'-B','-X','utf8',str(REPO/'script/cli/main.py')]
        def run(name,*args,content=None):
            result=subprocess.run(command+[name,'--config',str(self.config),*args],
                input=json.dumps(content,ensure_ascii=False) if content is not None else None,
                capture_output=True,text=True,encoding='utf8')
            response=json.loads(result.stdout)
            self.assertEqual(result.returncode,0,response)
            self.assertTrue(response['ok'],response)
            return response['data']
        raw={'raw_user_messages':[{'text':'命令行完整链','source':'simulation'}]}
        prepared=run('scene-prepare','--content-file','-',content=raw)
        node=prepared['scene']['node_id'];packet=self.director(node)
        root=str(self.root/'reader')
        ready=run('scene-submit','--node-id',node,'--source-packet-event-id',packet['packet_event_id'],
            '--output-root',root,'--content-file','-',content={'literary_text':'唯一的完整正文。','display':{'summary':'摘要','time':'时间','location':'地点','participants':[]}})
        files=[Path(ready['display']['snapshot_path']),Path(root)/'dist/index.html',Path(root)/'dist/display-version.js']
        before=[p.read_bytes() for p in files]
        jobs=run('capsule-check','--node-id',node)
        self.assertEqual(jobs['view'],'jobs')
        result=run('scene-archive','--node-id',node,'--output-root',root,'--content-file','-',content={'events':[],'default_source_event_ids':[ready['narrative_event_id']]})
        self.assertTrue(result['published'])
        self.assertEqual([p.read_bytes() for p in files],before)
        next_scene=run('scene-prepare','--content-file','-',content={'raw_user_messages':[{'text':'下一幕','source':'simulation'}]})
        self.assertEqual(next_scene['scene']['history_node_id'],node)
        self.assertEqual(next_scene['preparation']['previous_scene_prose'],'唯一的完整正文。')


    def test_submit_without_capsules_routes_directly_to_archive(self):
        from dataclasses import replace
        from copy import deepcopy
        settings=deepcopy(self.app.resources.settings);settings['creative']['capsule_mode']=False
        self.app.resources=replace(self.app.resources,settings=settings)
        self.root_node();node=self.open()['node_id'];packet=self.director(node)
        result=self.call('scene.submit',node_id=node,source_packet_event_id=packet['packet_event_id'],
            content={'literary_text':'不启用摘要','display':{'summary':'摘要','location':'地点','time':'时间','participants':[]}},
            output_root=str(self.root/'reader'),generate=False)
        self.assertEqual(result['next_operation'],'scene.archive')
