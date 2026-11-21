from common import FunctionalCase
from script.workflow.cli.api import Application

class CRUD(FunctionalCase):
    def test_crud_owned_query_and_binary_relation(self):
        self.call('node.begin',node_id='root',node_type='root');self.event();self.event(event_id='memory-2')
        self.call('record.update',entity='object',record_id='memory-player',patch={'name':'记忆线'})
        self.app.close();self.app=Application(self.config)
        page=self.call('object.events',object_id='memory-player',limit=1)
        self.assertEqual(page['total'],2);self.assertEqual(page['next_offset'],1)
        keys=list(page['items'][0])
        self.assertEqual(keys[0],'seq')
        self.assertEqual(page['items'][0]['event_action'],'append')
        self.assertEqual(keys[-2:],['created_time','modified_time'])
        self.assertFalse(any(k.startswith('res_') for k in keys))
        self.assertEqual(page['items'][0]['content']['自由栏目'],{'颜色':'蓝'})
        owners=self.call('record.list',entity='relation',filters={'relation_type':'event','target_object_id':'memory-player'})
        self.assertEqual(owners['total'],2)
        self.assertEqual({r['target_node_id'] for r in owners['items']},{'root'})
        self.call('relation.create',relation_id='reference',relation_type='event_reference',key_type='event',key_id='memory-2',target_event_id='memory-1')
        self.call('record.update',entity='relation',record_id='reference',patch={'state':'cancelled'})
        self.call('record.delete',entity='relation',record_id='reference')
        self.call('object.ensure',object_id='empty',object_type='truth',object_key='empty',name='待用真相')
        self.call('record.delete',entity='object',record_id='empty')
        self.assertIsNone(self.call('record.get',entity='object',record_id='empty'))
