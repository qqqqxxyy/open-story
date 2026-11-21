"""Selected design records, explicit event replacement, notes and open payloads."""
from creative_common import CreativeCase


class Business(CreativeCase):
    def test_published_root_maintenance_and_out_of_scene_input(self):
        self.root_node()
        raw='暂停创作，修改方向。\n  原始空格。'
        self.call('business.save',node_id='root',branch_id='main',kind='user_input',key='maintenance',content={'raw_user_messages':[{'text':raw,'source':'simulation'}]})
        self.call('business.save',node_id='root',branch_id='main',kind='plan',key='short',content={'text':'TEST_ROOT_PLAN'})
        self.assertEqual(self.call('business.read',node_id='root',branch_id='main',kind='user_input')['current'][0]['event']['content']['raw_user_messages'][0]['text'],raw)
        self.assertEqual(self.call('database.info')['counts']['node'],1)
        node=self.open()['node_id']
        recalled=self.call('scene.context',view='full',node_id=node)
        self.assertEqual(recalled['projection']['plan'][0]['event']['content']['text'],'TEST_ROOT_PLAN')

    def test_design_revisions_candidate_packet_and_notebook(self):
        self.root_node();node=self.open()['node_id']
        first=self.call('business.save',node_id=node,kind='truth',key='mystery',content={'text':'TEST_TRUTH_1','自由细节':[1,2]})['event']
        packet=self.director(node,design_notes={'candidates':[{'text':'TEST_UNUSED'}],'reason':'TEST_COMPARISON'},truth_event_ids=[first['event_id']])
        second=self.call('business.save',node_id=node,kind='truth',key='mystery',event_action='replace',target_event_ids=[first['event_id']],content={'text':'TEST_TRUTH_2'})['event']
        result=self.call('business.read',node_id=node,kind='truth',key='mystery',include_history=True)
        self.assertEqual([r['event']['content']['text'] for r in result['current']],['TEST_TRUTH_2'])
        self.assertEqual(len(result['history']),2)
        self.assertEqual(self.call('director.read',node_id=node,packet_event_id=packet['packet_event_id'])['brief']['design_notes']['candidates'][0]['text'],'TEST_UNUSED')
        self.call('business.save',node_id=node,kind='author_notes',key='voice',content={'text':'TEST_VOICE'})
        self.assertEqual(self.call('business.read',node_id=node,kind='author_notes')['current'][0]['event']['content']['text'],'TEST_VOICE')
        self.call('author.save',node_id=node,content={'literary_text':'TEST_PROSE'})
        self.finish(node)
        old=self.call('business.save',node_id=node,kind='plan',key='short',content={'text':'TEST_PLAN'})['event']
        self.call('business.save',node_id=node,kind='plan',key='short',event_action='replace',target_event_ids=[old['event_id']],content={'text':'TEST_NEW_PLAN'})
        self.assertEqual(self.call('node.read',node_id=node)['node']['state'],'active')
        self.assertEqual(self.call('business.read',node_id=node,kind='plan')['current'][0]['event']['content']['text'],'TEST_NEW_PLAN')

    def test_complete_fact_replace_thread_cancel_and_setting_change(self):
        self.root_node();node=self.open()['node_id']
        fact=self.call('business.save',node_id=node,kind='world_fact',key='fact-a',content={'id':'fact-a','text':'TEST_FACT_1','细节':'TEST_EXTRA'})['event']
        self.call('business.save',node_id=node,kind='world_fact',key='fact-a',event_action='replace',target_event_ids=[fact['event_id']],content={'id':'fact-a','text':'TEST_FACT_2'})
        thread=self.call('business.save',node_id=node,kind='thread',key='thread-a',content={'id':'thread-a','text':'TEST_THREAD','status':'open'})['event']
        self.call('business.save',node_id=node,kind='thread',key='thread-a',event_action='cancel',target_event_ids=[thread['event_id']],content={'reason':'TEST_RESOLVED'})
        self.call('business.save',node_id=node,kind='story_setting',key='narration',content={'person':'first','说明':'TEST_SETTING'})
        title=self.call('business.save',node_id=node,kind='story_setting',key='title',content='TEST_TITLE_1')['event']
        self.call('business.save',node_id=node,kind='story_setting',key='title',event_action='replace',target_event_ids=[title['event_id']],content='TEST_TITLE_2')
        titles=self.call('business.read',node_id=node,kind='story_setting',key='title')['current']
        self.assertEqual([r['event']['content'] for r in titles],['TEST_TITLE_2'])
        current=self.call('business.read',node_id=node,kind='world_fact')['current'][0]['event']['content']
        self.assertEqual(current,{'id':'fact-a','text':'TEST_FACT_2'})
        self.assertEqual(self.call('business.read',node_id=node,kind='thread')['current'],[])


    def test_content_source_indexes_and_user_input_keys(self):
        self.root_node();node=self.open(raw='SCENE_INPUT')['node_id']
        source=self.call('business.save',node_id=node,kind='role_memory',key='player',content={'character_id':'player','claim':'SOURCE_MEMORY'})['event']
        created=self.call('business.save',node_id=node,kind='world_fact',key='fact-a',source_event_ids=[source['event_id']],content={'id':'fact-a','text':'SOURCE_FACT'})
        self.assertEqual(created['event']['content']['source_event_ids'],[source['event_id']])
        first=self.call('business.save',node_id=node,kind='user_input',key='maintenance',content={'raw_user_messages':[{'text':'MAINTENANCE','source':'simulation'}]})
        other=self.call('business.save',node_id=node,kind='user_input',key='other',content={'raw_user_messages':[{'text':'OTHER','source':'simulation'}]})
        self.assertEqual(first['object_id'],other['object_id'])
        selected=self.call('business.read',node_id=node,kind='user_input',key='maintenance')
        self.assertEqual([row['event']['event_id'] for row in selected['current']],[first['event']['event_id']])
        self.assertEqual(self.call('record.list',entity='relation',filters={'relation_type':'creative_source'})['total'],0)


    def test_legacy_user_input_retry_returns_its_recorded_object(self):
        self.root_node();node=self.open()['node_id']
        content={'raw_user_messages':[{'text':'LEGACY_INPUT','source':'simulation'}]}
        stored={'payload':content,'_control':{'target_event_ids':[]}}
        self.call('event.create',node_id=node,
            object={'object_id':'user_input_maintenance','object_type':'user_input','object_key':'maintenance','name':'LEGACY'},
            event={'event_id':'legacy-input','event_type':'user_input','type_name':'maintenance','content':stored})
        before=self.call('database.info')['counts']
        replay=self.call('business.save',node_id=node,kind='user_input',key='maintenance',event_id='legacy-input',content=content)
        self.assertEqual(replay['object_id'],'user_input_maintenance')
        self.assertEqual(self.call('database.info')['counts'],before)
