from common import FunctionalCase

class Orchestration(FunctionalCase):
    def test_draft_publish_revision_and_current_pointers(self):
        self.root_node()
        draft=self.call('node.begin',node_id='scene-1',predecessor_id='root',branch_id='main')
        self.assertIsNone(draft['narrative_event_id']);self.assertIsNone(draft['summary_event_id'])
        self.assertEqual(list(draft)[0],'seq')
        self.assertEqual(list(draft)[-2:],['created_time','modified_time'])
        self.scene();self.scene('scene-2','scene-1')
        node=self.call('record.get',entity='node',record_id='scene-1')
        self.assertEqual(node['predecessor_node_id'],'root')
        self.assertEqual(node['summary_event_id'],'summary-scene-1')
        self.call('node.revise',node_id='scene-1',
            object={'object_id':'prose','object_type':'author_reply','object_key':'prose','name':'正文'},
            event={'event_id':'revision','event_type':'author_reply','type_name':'prose','content':{'literary_text':'他先关上了门。'}},select_as='narrative')
        self.assertEqual(self.call('node.read',node_id='scene-1')['narrative'],'他先关上了门。')
        self.assertEqual(self.call('record.get',entity='event',record_id='prose-scene-1')['content']['literary_text'],'铃声响起，他停下脚步。')
        self.assertEqual(self.call('record.list',entity='relation',filters={'relation_type':'node_narrative'})['total'],0)
        heads=self.call('record.list',entity='relation',filters={'relation_type':'branch_head','state':'active'})
        self.assertEqual(heads['items'][0]['target_node_id'],'scene-2')
    def test_leaf_cancel_and_delete_internal_relations(self):
        self.root_node();self.scene(publish=False);self.event(node='scene-1')
        self.call('relation.create',relation_id='internal',relation_type='related_material',key_type='event',key_id='memory-1',target_event_id='prose-scene-1')
        self.call('node.publish',node_id='scene-1')
        self.call('event.cancel',event_id='memory-1')
        self.assertEqual(self.call('object.events',object_id='memory-player',state='active')['total'],0)
        deleted=self.call('node.delete_leaf',node_id='scene-1')
        self.assertEqual(deleted['deleted_events'],3)
        self.assertIsNone(self.call('record.get',entity='node',record_id='scene-1'))
        self.assertEqual(self.call('database.info')['counts']['event'],0)
        heads=self.call('record.list',entity='relation',filters={'relation_type':'branch_head','state':'active'})
        self.assertEqual(heads['items'][0]['target_node_id'],'root')
