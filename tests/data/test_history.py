"""Read-only history, paragraph references, scope and constant query batching."""
from creative_common import CreativeCase


class History(CreativeCase):
    def test_search_read_and_inspect_without_new_scene(self):
        self.root_node();node=self.open()['node_id'];self.director(node)
        self.call('author.save',node_id=node,content={'literary_text':'第一段，铃声响起。\n\n第二段，他回头。'})
        self.finish(node)
        before=self.call('database.info')['counts']
        result=self.call('history.search',branch_id='main',keyword='铃声')
        self.assertEqual(result['matches'][0]['paragraph_index'],1)
        event_id=result['matches'][0]['narrative_event_id']
        read=self.call('history.read',view='full',branch_id='main',node_id=node,narrative_event_id=event_id)
        self.assertEqual(len(read['paragraphs']),2);self.assertIn('铃声',read['literary_text'])
        self.call('context.inspect',branch_id='main')
        self.assertEqual(self.call('database.info')['counts'],before)

    def test_search_batches_and_respects_cutoff(self):
        self.root_node();first=self.ordinary(raw='共同铃声');self.ordinary(raw='后来铃声')
        db=self.app.repository._store.db
        def search():
            statements=[];db.set_trace_callback(statements.append)
            try:result=self.call('history.search',branch_id='main',keyword='铃声')
            finally:db.set_trace_callback(None)
            return result,len([s for s in statements if s.lstrip().upper().startswith(('SELECT','WITH'))])
        _,one=search();self.ordinary(raw='更多铃声');_,many=search()
        self.assertEqual(one,many)
        cutoff=self.call('history.search',branch_id='main',at_node_id=first,keyword='铃声')
        self.assertEqual({match['node_id'] for match in cutoff['matches']},{first})


    def test_recent_index_views_and_grouped_search_share_fixed_history(self):
        self.root_node()
        first=self.ordinary(raw='第一幕铃声')
        second=self.ordinary(raw='第二幕兔子')
        third=self.ordinary(raw='第三幕铃声兔子')
        before=self.call('database.info')['counts']
        index=self.call('history.list',branch_id='main',limit=2)
        self.assertEqual([i['node_id'] for i in index['items']],[second,third])
        self.assertEqual(index['next_offset'],2)
        older=self.call('history.list',branch_id='main',limit=2,offset=2)
        self.assertEqual([i['node_id'] for i in older['items']],[first])
        self.assertTrue(all(i['summary_event_id'] and i['summary']=='TEST_SUMMARY' for i in index['items']))
        prose=self.call('history.read',branch_id='main',node_id=third)
        self.assertNotIn('paragraphs',prose)
        paragraphs=self.call('history.read',branch_id='main',node_id=third,view='paragraphs')
        self.assertNotIn('literary_text',paragraphs)
        full=self.call('history.read',branch_id='main',node_id=third,view='full')
        self.assertEqual(prose['literary_text'],full['literary_text'])
        self.assertEqual(paragraphs['paragraphs'],full['paragraphs'])
        db=self.app.repository._store.db
        statements=[];db.set_trace_callback(statements.append)
        try:grouped=self.call('history.search',branch_id='main',keywords=['铃声','兔子'],limit=1)
        finally:db.set_trace_callback(None)
        grouped_count=len([s for s in statements if s.lstrip().upper().startswith(('SELECT','WITH'))])
        for group in grouped['results']:
            statements=[];db.set_trace_callback(statements.append)
            try:single=self.call('history.search',branch_id='main',keyword=group['keyword'],limit=1)
            finally:db.set_trace_callback(None)
            self.assertEqual({k:v for k,v in group.items() if k!='keyword'},{k:v for k,v in single.items() if k!='scope'})
            self.assertEqual(grouped_count,len([s for s in statements if s.lstrip().upper().startswith(('SELECT','WITH'))]))
        fixed=self.open()['node_id']
        self.assertEqual([i['node_id'] for i in self.call('history.list',scene_node_id=fixed)['items']],[first,second,third])
        self.assertEqual(self.call('database.info')['counts']['node'],before['node']+1)
