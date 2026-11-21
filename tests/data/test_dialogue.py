"""Two normal dialogue turns, replay and one authoritative composed scene."""
import json
import subprocess
import sys
from common import REPO
from creative_common import CreativeCase


class Dialogue(CreativeCase):
    def test_two_turns_close_preserves_inputs_fragments_and_one_scene(self):
        self.root_node()
        opened=self.open('dialogue',raw='TEST_QUESTION_1');node=opened['node_id']
        self.director(node)
        first_turn=opened['raw_input_event_ids'][0]
        first={'literary_text':'TEST_QUESTION_1\nTEST_ANSWER_1','scene_complete':False,'feedback':{}}
        saved=self.call('dialogue.save',node_id=node,turn_id=first_turn,content=first)
        replay=self.call('dialogue.save',node_id=node,turn_id=first_turn,content=first)
        self.assertEqual(saved,replay)
        turn=self.call('dialogue.input',node_id=node,content={'raw_user_messages':[{'text':'TEST_QUESTION_2','source':'simulation'}]})
        self.assertEqual(len(turn['raw_user_messages']),1)
        second={'literary_text':'TEST_QUESTION_2\nTEST_ANSWER_2','scene_complete':True,'feedback':{'变化':'TEST_DIALOGUE_CHANGE'}}
        self.call('dialogue.save',node_id=node,turn_id=turn['turn_id'],content=second)
        reply=self.call('author.read',node_id=node)
        self.assertEqual(reply['literary_text'],first['literary_text']+'\n\n'+second['literary_text'])
        narrative=self.call('record.get',entity='event',record_id=reply['narrative_event_id'])
        self.assertNotIn('literary_text',narrative['content'])
        self.assertEqual(len(narrative['content']['fragment_event_ids']),2)
        self.assertNotIn('dialogue_fragment_event_ids',reply['reply'])
        self.assertEqual(self.call('record.list',entity='relation',filters={'relation_type':'creative_source'})['total'],0)
        self.finish(node)
        self.assertEqual(self.call('database.info')['counts']['node'],2)
        self.assertEqual(self.call('node.read',node_id=node)['narrative'],reply['literary_text'])
        self.assertEqual(len(self.call('dialogue.read',node_id=node)['inputs']),2)

    def test_explicit_close_adds_only_new_closing_fragment(self):
        self.root_node();opened=self.open('dialogue');node=opened['node_id'];self.director(node)
        self.call('dialogue.save',node_id=node,turn_id=opened['raw_input_event_ids'][0],content={'literary_text':'TEST_TURN','scene_complete':False})
        receipt=self.call('dialogue.close',node_id=node,content={'closing_text':'TEST_CLOSING'})
        complete=self.call('author.read',node_id=node,packet_event_id=receipt['packet_event_id'])
        self.assertEqual(complete['literary_text'],'TEST_TURN\n\nTEST_CLOSING')
        narrative=self.call('record.get',entity='event',record_id=complete['narrative_event_id'])
        self.assertNotIn('dialogue_fragment_event_ids',complete['reply'])
        closing=self.call('dialogue.read',node_id=node,fragment_event_id=narrative['content']['fragment_event_ids'][-1])
        self.assertEqual(closing['fragments'][0]['content']['literary_text'],'TEST_CLOSING')
        self.assertEqual(closing['inputs'],[])


    def test_author_cli_turn_receipt_and_director_incremental_read(self):
        self.root_node(); scene=self.open('dialogue',raw='TEST_TURN_ONE'); node=scene['node_id']
        self.director(node)
        command=[sys.executable,'-B','-X','utf8',str(REPO/'script/cli/main.py')]

        def run(*args, content=None):
            result=subprocess.run(command+list(args),input=json.dumps(content,ensure_ascii=False) if content is not None else None,
                                  capture_output=True,text=True,encoding='utf8',check=True)
            self.assertEqual(result.stderr,'')
            response=json.loads(result.stdout);self.assertTrue(response['ok'],response)
            return response['data']

        first={'literary_text':'TEST_TURN_ONE\nTEST_RESPONSE_ONE','scene_complete':False,'feedback':{}}
        receipt=run('dialogue-turn-save','--config',str(self.config),'--node-id',node,
                    '--turn-id',scene['raw_input_event_ids'][0],'--content-file','-',content=first)
        second_input=self.call('dialogue.input',node_id=node,content={'raw_user_messages':[{'text':'TEST_TURN_TWO','source':'simulation'}]})
        increment=self.call('context.read',node_id=node,event_ids=[second_input['turn_id']])
        self.assertEqual(len(increment['sources']),1)
        self.assertEqual(increment['sources'][0]['event']['content']['raw_user_messages'][0]['text'],'TEST_TURN_TWO')
        second={'literary_text':'TEST_TURN_TWO\nTEST_RESPONSE_TWO','scene_complete':True,'feedback':{'note':'TEST_COMPLETED'}}
        completed=run('dialogue-turn-save','--config',str(self.config),'--node-id',node,
                      '--turn-id',second_input['turn_id'],'--content-file','-',content=second)
        received=run('dialogue-read','--config',str(self.config),'--node-id',node,
                     '--fragment-event-id',receipt['fragment_event_id'])
        self.assertEqual([f['event_id'] for f in received['fragments']],[receipt['fragment_event_id']])
        self.assertEqual(received['fragments'][0]['content']['literary_text'],first['literary_text'])
        self.assertEqual([i['event_id'] for i in received['inputs']],scene['raw_input_event_ids'])
        final_turn=self.call('dialogue.read',node_id=node,fragment_event_id=completed['fragment_event_id'])
        self.assertEqual(final_turn['inputs'][0]['event_id'],second_input['turn_id'])
        self.assertTrue(final_turn['fragments'][0]['content']['scene_complete'])
        restored=self.call('dialogue.read',node_id=node)
        self.assertEqual(len(restored['fragments']),2)
        self.assertEqual(len(restored['inputs']),2)
        full=run('author-reply-read','--config',str(self.config),'--node-id',node,
                 '--packet-event-id',completed['packet_event_id'])
        self.assertEqual(full['literary_text'],first['literary_text']+'\n\n'+second['literary_text'])
        self.assertEqual(full['feedback'],second['feedback'])
        self.finish(node)


    def test_completed_dialogue_submits_existing_packet_once(self):
        self.root_node()
        prepared=self.call('scene.prepare',mode='dialogue',content={'raw_user_messages':[{'text':'问','source':'simulation'}]})
        node=prepared['scene']['node_id'];self.director(node)
        turn=prepared['scene']['raw_input_event_ids'][0]
        complete=self.call('dialogue.save',node_id=node,turn_id=turn,content={'literary_text':'答','scene_complete':True})
        ready=self.call('scene.submit',node_id=node,author_packet_event_id=complete['packet_event_id'],content={'display':{'summary':'问答','location':'地点','time':'时间','participants':[]}},output_root=str(self.root/'reader'))
        self.assertEqual(ready['narrative_event_id'],complete['narrative_event_id'])
        self.assertNotIn('literary_text',ready)
        self.assertTrue(self.call('scene.archive',node_id=node,content={'events':[]},output_root=str(self.root/'reader'))['published'])
