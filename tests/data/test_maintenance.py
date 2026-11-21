"""Normal range confirmation, atomic restart and external-reference protection."""
from creative_common import CreativeCase
from script.cli.main import execute


class Maintenance(CreativeCase):
    def request(self,name,**params):
        params.setdefault('output_root',str(self.root/'reader'));params.setdefault('generate',False)
        return self.call(name,**params)

    def assert_heads(self):
        nodes=self.call('record.list',entity='node')['items']
        parents={n['predecessor_node_id'] for n in nodes}
        heads=self.call('record.list',entity='relation',filters={'relation_type':'branch_head'})['items']
        self.assertEqual({n['node_id'] for n in nodes if n['node_id'] not in parents},{h['target_node_id'] for h in heads})
        self.assertEqual(len(heads),len({h['target_node_id'] for h in heads}))

    def test_descendants_keep_anchor_confirm_then_delete_both_branches(self):
        self.root_node();anchor=self.ordinary();main=self.ordinary()
        self.call('branch.fork',branch_id='alt',from_node_id=anchor,node_id='alt-node')
        params={'node_id':anchor,'branch_id':'main','include_target':False}
        before=self.call('database.info')['counts']
        snapshot=self.root/'reader/story/functional/story.json'
        saved_snapshot=snapshot.read_bytes()
        first=self.request('node.delete',**params)
        self.assertEqual(first['status'],'confirmation_required')
        self.assertEqual(set(first['proposal']['deleted_node_ids']),{main,'alt-node'})
        self.assertEqual(self.call('database.info')['counts'],before)
        self.assertEqual(snapshot.read_bytes(),saved_snapshot)
        done=self.request('node.delete',**params,user_confirmed=True,confirmation_token=first['proposal']['confirmation_token'])
        self.assertEqual(done['status'],'deleted');self.assert_heads()
        self.assertEqual(self.call('branch.read',branch_id='main')['head']['node_id'],anchor)
        self.assertIsNone(self.call('branch.read',branch_id='alt')['head'])
        self.assertIsNotNone(self.call('record.get',entity='object',record_id='alt'))

    def test_changed_range_needs_new_confirmation_and_external_refs_block(self):
        self.root_node();anchor=self.ordinary();self.ordinary();last=self.ordinary()
        first=self.request('node.delete',node_id=anchor)
        self.ordinary()
        changed=self.request('node.delete',node_id=anchor,user_confirmed=True,confirmation_token=first['proposal']['confirmation_token'])
        self.assertEqual(changed['status'],'confirmation_required')
        self.assertNotEqual(first['proposal']['confirmation_token'],changed['proposal']['confirmation_token'])
        self.call('object.ensure',object_id='retained-reference',object_type='test',object_key='test',name='test')
        self.call('relation.create',relation_type='test_reference',key_type='object',key_id='retained-reference',target_node_id=last)
        count=self.call('database.info')['counts']
        failed=execute(self.app,{'operation':'node.delete','params':{'node_id':anchor,'include_target':False,'generate':False}})
        self.assertFalse(failed['ok']);self.assertEqual(failed['error']['code'],'EXTERNAL_DEPENDENCY')
        self.assertEqual(self.call('database.info')['counts'],count)

    def test_leaf_rewrite_new_id_parent_inputs_and_retry(self):
        self.root_node();old=self.ordinary(raw='原始开幕输入。')
        content={'raw_user_messages':[{'text':'请重写这一幕。','source':'simulation'}]}
        result=self.request('node.rewrite',node_id=old,branch_id='main',content=content)
        self.assertEqual(result['status'],'rewritten')
        new=result['scene']['node_id'];self.assertNotEqual(new,old)
        self.assertIsNone(self.call('record.get',entity='node',record_id=old))
        node=self.call('record.get',entity='node',record_id=new)
        self.assertEqual(node['state'],'creating');self.assertEqual(node['predecessor_node_id'],'root')
        rows=self.call('node.events',node_id=new)['items']
        inputs=next(row for row in rows if row['event_type']=='user_input')['content']['raw_user_messages']
        self.assertEqual([m['text'] for m in inputs],['原始开幕输入。','请重写这一幕。'])
        self.assertFalse(any(row['event_type']=='narrative' for row in rows));self.assert_heads()
        retried=self.request('node.rewrite',node_id=old,branch_id='main',content=content)
        self.assertTrue(retried['already_done']);self.assertEqual(retried['scene']['node_id'],new)
        self.director(new);self.call('author.save',node_id=new,content={'literary_text':'NEW_PROSE'})
        self.finish(new);self.assert_heads()

    def test_rewrite_nonleaf_requires_its_own_confirmation(self):
        self.root_node();old=self.ordinary();self.ordinary()
        params={'node_id':old,'branch_id':'main','content':{'raw_user_messages':[{'text':'重创','source':'simulation'}]}}
        first=self.request('node.rewrite',**params)
        self.assertEqual(first['status'],'confirmation_required');self.assertEqual(first['proposal']['node_count'],2)
        second=self.request('node.rewrite',**params,user_confirmed=True,confirmation_token=first['proposal']['confirmation_token'])
        self.assertEqual(second['status'],'rewritten');self.assert_heads()
