"""Normal initialization workflows through the public API and actual CLI."""
from pathlib import Path
from dataclasses import replace
import json
import subprocess
import sys
import tempfile
import unittest
from common import REPO
from script.cli.main import execute
from script.cli.bootstrap import bootstrap
from script.workflow.cli.api import Application


class Initialization(unittest.TestCase):
    backend = 'sqlite'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='openstory-init-functional-')
        self.root = Path(self.temp.name)
        self.app = Application(data_root=self.root / 'story-data',
                               resources=replace(bootstrap(), project_root=self.root/'unconfigured-skill'))

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def request(self, **overrides):
        params = {
            'story_id': 'test-world-a', 'title': 'TEST_TITLE_A',
            'settings': {'background': {'地点': 'TEST_LOCATION_A'}, 'tone': ['TEST_TONE_A'],
                         '自由设定': {'任意栏目': [1, {'细节': '保持开放'}]}},
            'raw_user_messages': [{'text': '原始输入\n保留错字，和  空格。', 'source': 'simulation', '说明': {'自由来源备注': True}},
                                  {'text': '第二轮确认：“按这个来”。\n'}],
        }
        params.update(overrides)
        params['content'] = {'settings': params.pop('settings'), 'raw_user_messages': params.pop('raw_user_messages')}
        return {'operation': 'story_init', 'params': params}

    def call(self, app, request):
        response = execute(app, request)
        self.assertTrue(response['ok'], response)
        return response['data']

    def test_online_root_settings_raw_input_and_same_request_retry(self):
        request = self.request()
        result = self.call(self.app, request)
        self.assertEqual(Path(result['database_path']), self.root / 'story-data/online/test-world-a/story.sqlite3')
        self.assertFalse(result['already_initialized'])
        self.assertEqual(result['counts'], {'node': 1, 'object': 6, 'event': 6, 'relation': 7})
        stored_config = json.loads(Path(result['config_path']).read_text(encoding='utf-8'))
        self.assertEqual(set(stored_config), {'database_id', 'backend', 'location', 'busy_timeout_ms'})
        reader = Application(result['config_path'])
        try:
            read = self.call(reader, {'operation': 'node.read', 'params': {'node_id': 'node-root', 'branch_id': 'main'}})
            self.assertEqual(read['node']['state'], 'active')
            self.assertIsNone(read['narrative'])
            self.assertIsNone(read['summary'])
            branch = self.call(reader, {'operation': 'branch.read', 'params': {'branch_id': 'main'}})
            self.assertEqual(branch['head']['node_id'], 'node-root')
            inputs = self.call(reader, {'operation': 'node.events', 'params': {
                'branch_id': 'main', 'node_id': 'node-root', 'event_type': 'user_input'}})
            self.assertEqual([e['content']['text'] for e in inputs['items']], [m['text'] for m in request['params']['content']['raw_user_messages']])
            settings = self.call(reader, {'operation': 'object.events', 'params': {
                'branch_id': 'main', 'object_id': 'story_setting_自由设定'}})
            self.assertEqual(settings['items'][0]['content'], request['params']['content']['settings']['自由设定'])
            self.assertNotIn('protagonist', result['settings'])
            self.assertNotIn('narration', result['settings'])
            self.assertEqual(inputs['items'][0]['content']['source'], 'simulation')
            self.assertEqual(inputs['items'][1]['content']['source'], 'assistant_transcribed')
            self.assertEqual(inputs['items'][0]['content']['说明'], {'自由来源备注': True})
        finally:
            reader.close()
        again = self.call(self.app, request)
        self.assertTrue(again['already_initialized'])
        self.assertEqual(again['counts'], result['counts'])

    def test_debug_target_and_explicit_protagonist(self):
        protagonist = {'name': 'TEST_PLAYER_B', '性格': ['TEST_TRAIT_B'], '补充': {'自由结构': True}}
        result = self.call(self.app, self.request(environment='debug', settings={
            'background': 'TEST_BACKGROUND_B', 'protagonist': protagonist, 'narration': {'person': 'first', '自由视角备注': True}}))
        self.assertEqual(Path(result['config_path']), self.root / 'story-data/debug/test-world-a/sqlite.json')
        reader = Application(result['config_path'])
        try:
            stored = self.call(reader, {'operation': 'object.events', 'params': {
                'branch_id': 'main', 'object_id': 'story_setting_protagonist'}})
            self.assertEqual(stored['items'][0]['content'], protagonist)
            narration = self.call(reader, {'operation': 'object.events', 'params': {
                'branch_id': 'main', 'object_id': 'story_setting_narration'}})['items'][0]['content']
            self.assertEqual(narration, {'person': 'first', '自由视角备注': True})
        finally:
            reader.close()

    def test_real_cli_without_config_file_and_stdin(self):
        request = self.request(story_id='test-cli-world')
        path = self.root / 'request.json'
        path.write_text(json.dumps(request['params']['content'], ensure_ascii=False), encoding='utf-8')
        command = [sys.executable, '-B', '-X', 'utf8', str(REPO / 'script/cli/main.py'),
                   'story-init', '--story-id', 'test-cli-world', '--title', 'TEST_TITLE_A',
                   '--data-root', str(self.root / 'cli-data'), '--content-file', str(path)]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', check=True)
        created = json.loads(result.stdout)
        self.assertTrue(created['ok'])
        self.assertTrue(Path(created['data']['database_path']).is_file())
        result = subprocess.run(command[:-1] + ['-'], input=json.dumps(request['params']['content'], ensure_ascii=False),
                                capture_output=True, text=True, encoding='utf-8', check=True)
        repeated = json.loads(result.stdout)
        self.assertTrue(repeated['data']['already_initialized'])
        self.assertEqual(created['data']['counts'], repeated['data']['counts'])

    def test_first_scene_entry_after_initialization(self):
        created = self.call(self.app, self.request())
        reader = Application(created['config_path'])
        try:
            result = self.call(reader, {'operation':'scene_next','params':{'content':{'raw_user_messages':[{'text':'TEST_FIRST_SCENE','source':'simulation'}]}}})
            self.assertEqual(result['history_node_id'],'node-root')
            self.assertEqual(result['status'],'preparing')
            inputs=self.call(reader,{'operation':'record.list','params':{'entity':'relation','filters':{'relation_type':'event','target_object_id':'user_input_workflow'}}})
            self.assertEqual({row['target_node_id'] for row in inputs['items']},{'node-root',result['node_id']})
            self.assertEqual(self.call(reader,{'operation':'database.info','params':{}})['counts']['node'],2)
        finally:
            reader.close()


    def test_existing_v6_initialization_retry_preserves_history(self):
        import sqlite3
        from contextlib import closing
        request=self.request()
        result=self.call(self.app,request)
        config=Path(result['config_path'])
        metadata=json.loads(config.read_text(encoding='utf8'))
        metadata['skill_version']=6
        config.write_text(json.dumps(metadata),encoding='utf8')
        with closing(sqlite3.connect(result['database_path'])) as db, db:
            identity=json.loads(db.execute("SELECT content FROM event WHERE event_id='init-story'").fetchone()[0])
            self.assertNotIn('skill_version',identity)
            identity['skill_version']=6
            original=json.dumps(identity,ensure_ascii=False)
            db.execute("UPDATE event SET content=? WHERE event_id='init-story'",(original,))
            db.execute('PRAGMA user_version=6')
        before=config.read_bytes()
        retry=self.call(self.app,request)
        self.assertTrue(retry['already_initialized'])
        self.assertEqual(config.read_bytes(),before)
        with closing(sqlite3.connect(result['database_path'])) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],6)
            self.assertEqual(db.execute("SELECT content FROM event WHERE event_id='init-story'").fetchone()[0],original)
