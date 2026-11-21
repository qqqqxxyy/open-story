from common import FunctionalCase

class Branch(FunctionalCase):
    def assert_leaf_heads(self):
        nodes=self.call('record.list',entity='node')['items']
        heads=self.call('record.list',entity='relation',filters={'relation_type':'branch_head'})['items']
        parents={n['predecessor_node_id'] for n in nodes if n['predecessor_node_id']}
        leaves={n['node_id'] for n in nodes if n['node_id'] not in parents}
        self.assertEqual({h['target_node_id'] for h in heads},leaves)
        self.assertEqual(len(heads),len(leaves))
        self.assertEqual(len({h['key_id'] for h in heads}),len(heads))
        self.assertEqual({h['state'] for h in heads},{'active'})
        self.assertEqual(self.call('record.list',entity='relation',filters={'relation_type':'node_branch'})['total'],0)

    def test_fork_scope_projection_and_inactive_branch_after_delete(self):
        self.root_node();self.scene(publish=False)
        self.event(node='scene-1',event_id='shared');self.call('node.publish',node_id='scene-1')
        self.scene('main-2','scene-1',publish=False)
        self.event(node='main-2',event_id='only-main');self.call('node.publish',node_id='main-2')
        made=self.call('branch.fork',branch_id='alternative',from_node_id='scene-1',node_id='alt-2',name='另一条线')
        self.assertEqual(made['head']['state'],'creating');self.assert_leaf_heads()
        self.scene('alt-2','scene-1',publish=False,branch='alternative')
        self.event(node='alt-2',event_id='only-alt',branch_id='alternative')
        self.call('node.publish',node_id='alt-2',branch_id='alternative')
        main=self.call('object.events',object_id='memory-player')
        self.assertEqual([e['event_id'] for e in main['items']],['shared','only-main'])
        alt=self.call('events.query',branch_id='alternative',object_ids=['memory-player'],fields=['event_id'],include_total=False,limit=1)
        self.assertEqual(alt['items'],[{'event_id':'shared'}]);self.assertIsNone(alt['total']);self.assertEqual(alt['next_offset'],1)
        alt=self.call('events.query',branch_id='alternative',object_ids=['memory-player'],fields=['event_id'],include_total=False,offset=1,limit=1)
        self.assertEqual(alt['items'],[{'event_id':'only-alt'}]);self.assertIsNone(alt['next_offset'])
        cutoff=self.call('object.events',branch_id='alternative',at_node_id='scene-1',object_id='memory-player')
        self.assertEqual([e['event_id'] for e in cutoff['items']],['shared'])
        scope=self.call('branch.scope',branch_id='alternative')
        self.assertEqual(scope['node_ids'],['root','scene-1','alt-2'])
        self.assertEqual(self.call('node.branch',node_id='alt-2')['branch']['object_id'],'alternative')
        self.assertIsNone(self.call('node.branch',node_id='scene-1'))
        removed=self.call('node.delete_leaf',node_id='alt-2',branch_id='alternative')
        self.assertEqual(removed['branch_status'],'inactive')
        self.assertIsNotNone(self.call('record.get',entity='object',record_id='alternative'))
        self.assertIsNone(self.call('branch.read',branch_id='alternative')['head']);self.assert_leaf_heads()
        removed=self.call('node.delete_leaf',node_id='main-2')
        self.assertEqual(removed['head_node_id'],'scene-1');self.assert_leaf_heads()

    def test_compound_filters_and_current_head_after_continuation(self):
        self.root_node()
        initial_head=self.call('record.list',entity='relation',filters={'relation_type':'branch_head'})['items'][0]['relation_id']
        self.scene(publish=False)
        self.event(node='scene-1',event_id='memory-a',object_id='person-a')
        self.event(node='scene-1',event_id='memory-b',object_id='person-b')
        self.call('node.publish',node_id='scene-1');self.assert_leaf_heads()
        result=self.call('events.query',branch_id='main',object_ids=['person-a','person-b'],event_types=['role_memory'],state='active',fields=['event_id','content'])
        self.assertEqual([e['event_id'] for e in result['items']],['memory-a','memory-b'])
        self.assertEqual(result['total'],2)
        self.scene('scene-2','scene-1');self.assert_leaf_heads()
        self.assertEqual(self.call('branch.read',branch_id='main')['head']['node_id'],'scene-2')
        self.assertEqual(self.call('record.list',entity='relation',filters={'relation_type':'branch_head'})['items'][0]['relation_id'],initial_head)
