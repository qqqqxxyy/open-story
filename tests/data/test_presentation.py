"""SQLite source -> public snapshot -> real offline HTML in an isolated directory."""
import json
import re
from pathlib import Path
from hashlib import sha256
from script.workflow.pipeline.creative.presentation import body_revision
from creative_common import CreativeCase


class Presentation(CreativeCase):
    def test_real_html_pending_then_archived_without_backend_secrets(self):
        self.root_node();node=self.open()['node_id']
        secret=self.call('business.save',node_id=node,kind='secret',key='test',content={'text':'TEST_NEVER_EXPORT'})
        self.director(node,truth_event_ids=[secret['event']['event_id']])
        self.call('author.save',node_id=node,content={'literary_text':'TEST_PUBLIC_PROSE','feedback':{'私下':'TEST_NEVER_EXPORT'}})
        first=self.call('scene.display',node_id=node,content={'summary':'TEST_SUMMARY','location':'TEST_LOCATION','time':'TEST_TIME','participants':['player']},
                        output_root=str(self.root/'reader'),generate=True)
        snapshot=json.loads(Path(first['snapshot_path']).read_text(encoding='utf8'))
        self.assertFalse(snapshot['chapters'][0]['display']['pending'])
        self.assertNotIn('TEST_NEVER_EXPORT',json.dumps(snapshot))
        html=(self.root/'reader/dist/index.html').read_text(encoding='utf8')
        self.assertIn('TEST_PUBLIC_PROSE',html)
        embedded=json.loads(re.search(r'<script type="application/json" id="story-data">([\s\S]*?)</script>',html).group(1))
        self.assertEqual(embedded['stories'][0]['chapters'][0]['display'],snapshot['chapters'][0]['display'])
        state=self.call('scene.status',node_id=node,output_root=str(self.root/'reader'))
        self.assertTrue(state['display_snapshot_available'])
        self.assertTrue(state['display_html_available'])
        self.assertNotIn('TEST_NEVER_EXPORT',html)
        self.finish(node,generate=True)
        final=json.loads((self.root/'reader/story/functional/story.json').read_text(encoding='utf8'))
        self.assertFalse(final['chapters'][0]['display']['pending'])
        self.assertEqual(len(final['chapters']),1)
        self.assertEqual(final['chapters'][0]['display']['key'],snapshot['chapters'][0]['display']['key'])

    def test_revision_matches_ecmascript_normalization_without_modifying_prose(self):
        for raw, normalized in (
            ('正文\r\n第二段\r\n', '正文\n第二段'),
            ('正文\n\u00a0\ufeff', '正文'),
            ('正文\u0085', '正文\u0085'),
            ('行尾  \n下一行', '行尾  \n下一行'),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(body_revision(raw), sha256(normalized.encode('utf8')).hexdigest())

    def test_api_preview_archive_and_export_keep_body_and_revision(self):
        self.root_node()
        node = self.open()['node_id']
        self.director(node)
        prose = '完整正文。\r\n\r\n第二段。\r\n\u00a0\ufeff'
        self.call('author.save', node_id=node, content={'literary_text':prose,'feedback':{}})
        output = self.root/'reader'
        self.call('scene.display', node_id=node,
                  content={'summary':'摘要','location':'地点','time':'时间','participants':['player']},
                  output_root=str(output), generate=False)
        path = output/'story/functional/story.json'
        preview = json.loads(path.read_text(encoding='utf8'))['chapters'][0]
        self.assertEqual(preview['narrative'],prose)
        self.assertEqual(preview['display']['revision'],body_revision(prose))
        self.assertFalse(preview['display']['pending'])
        status = self.call('scene.status', node_id=node, output_root=str(output))
        self.assertTrue(status['display_snapshot_available'])
        self.assertFalse(status['display_html_available'])
        self.call('scene.archive', node_id=node,content={'events':[]},output_root=str(output))
        archived = json.loads(path.read_text(encoding='utf8'))['chapters'][0]
        self.assertEqual(archived['narrative'],prose)
        self.assertEqual(archived['display']['key'],preview['display']['key'])
        self.assertEqual(archived['display']['revision'],preview['display']['revision'])
        self.assertFalse(archived['display']['pending'])
        self.call('display.export', output_root=str(output),generate=True)
        exported = json.loads(path.read_text(encoding='utf8'))['chapters'][0]
        self.assertEqual(exported['display'],archived['display'])
        status = self.call('scene.status', node_id=node, output_root=str(output))
        self.assertTrue(status['published'])
        self.assertTrue(status['display_snapshot_available'])
        self.assertTrue(status['display_html_available'])
        self.assertEqual(self.call('author.read',node_id=node)['literary_text'],prose)


    def test_rebuild_current_frontend_from_v6_database_without_old_snapshots(self):
        self.root_node();node=self.open()['node_id'];self.director(node)
        self.call('author.save',node_id=node,content={'literary_text':'REBUILT_FROM_DATABASE','feedback':{}})
        self.call('scene.display',node_id=node,content={'summary':'摘要','location':'测试地','time':'测试时','participants':[]},output_root=str(self.root/'first'),generate=False)
        store=self.app.repository._store
        store.db.execute('PRAGMA user_version=6')
        config_before=self.config.read_bytes()
        result=self.call('display.export',output_root=str(self.root/'clean-rebuild'),generate=True)
        snapshot=json.loads(Path(result['snapshot_path']).read_text(encoding='utf8'))
        self.assertEqual(snapshot['source_kind'],'open_story')
        self.assertNotIn('version',snapshot)
        self.assertNotIn('sourceVersion',snapshot)
        self.assertIn('REBUILT_FROM_DATABASE',Path(result['html_path']).read_text(encoding='utf8'))
        self.assertEqual(store.skill_version,6)
        self.assertEqual(self.config.read_bytes(),config_before)


    def test_archive_and_retry_never_republish_complete_display(self):
        self.root_node();node=self.open()['node_id'];self.director(node)
        self.call('author.save',node_id=node,content={'literary_text':'READY_ONCE','feedback':{}})
        root=self.root/'reader'
        first=self.call('scene.display',node_id=node,content={'summary':'完整摘要','location':'地点','time':'时间','participants':[]},output_root=str(root),generate=True)
        files=[Path(first['snapshot_path']),root/'dist/index.html',root/'dist/display-version.js']
        before=[p.read_bytes() for p in files]
        self.assertEqual(first['publication_status'],'published')
        self.assertEqual(first['changed_node_ids'],[node])
        for repeat in range(2):
            result=self.call('scene.archive',node_id=node,content={'events':[]},output_root=str(root))
            self.assertTrue(result['published'])
            self.assertEqual([p.read_bytes() for p in files],before)
        again=self.call('scene.display',node_id=node,content={'summary':'完整摘要','location':'地点','time':'时间','participants':[]},output_root=str(root),generate=True)
        self.assertEqual(again['publication_status'],'unchanged')
        self.assertEqual(again['changed_node_ids'],[])
        self.assertEqual([p.read_bytes() for p in files],before)


    def test_retry_repairs_marker_when_html_already_contains_saved_scene(self):
        self.root_node();node=self.open()['node_id'];self.director(node)
        self.call('author.save',node_id=node,content={'literary_text':'MARKER_REPAIR','feedback':{}})
        root=self.root/'reader';metadata={'summary':'摘要','location':'地点','time':'时间','participants':[]}
        first=self.call('scene.display',node_id=node,content=metadata,output_root=str(root),generate=True)
        marker=root/'dist/display-version.js'
        marker.write_text('window.storyDisplayVersionReceived?.('+json.dumps({'contentRevision':'0'*64,'storyRevisions':{}})+');',encoding='utf8')
        repaired=self.call('scene.display',node_id=node,content=metadata,output_root=str(root),generate=True)
        self.assertEqual(repaired['publication_status'],'published')
        self.assertFalse(repaired['snapshot_changed'])
        html=(root/'dist/index.html').read_text(encoding='utf8')
        revision=re.search(r'name="story-display-revision" content="([a-f0-9]{64})"',html).group(1)
        self.assertIn(revision,marker.read_text(encoding='utf8'))
