"""Normal-use CLI mapping for controls, nested records and open content."""
from common import FunctionalCase, REPO
import json
import subprocess
import sys


class CLI(FunctionalCase):
    def command(self, operation, *arguments, input=None):
        command = [sys.executable, '-B', '-X', 'utf8', str(REPO / 'script/cli/main.py'),
                   operation, '--config', str(self.config), *arguments]
        process = subprocess.run(command, input=input, capture_output=True, text=True,
                                 encoding='utf-8', check=True)
        response = json.loads(process.stdout)
        self.assertTrue(response['ok'], response)
        return response['data']

    def test_control_flags_create_and_read_object(self):
        obj = self.command('object-ensure', '--object-id', 'cli-truth', '--object-type', 'truth',
                           '--object-key', 'bell', '--name', '铃声的真相')
        self.assertEqual(obj['name'], '铃声的真相')
        stored = self.command('record-get', '--entity', 'object', '--record-id', 'cli-truth')
        self.assertEqual(stored['object_id'], 'cli-truth')

    def test_event_content_file_stdin_projection_and_generated_identity(self):
        self.root_node()
        self.scene(publish=False)
        content = {'claim': '原话\n“保留引号”、空格  和错字。', '自由栏目': {'未知结构': [1, True, '声音']}}
        path = self.root / 'content.json'
        path.write_text(json.dumps(content, ensure_ascii=False), encoding='utf-8')
        controls = ['--branch-id', 'main', '--node-id', 'scene-1', '--object-id', 'cli-memory',
                    '--object-type', 'role_memory', '--object-key', 'player', '--name', '人物记忆',
                    '--event-type', 'role_memory', '--type-name', 'player', '--content-file']
        first = self.command('event-create', *controls, str(path))
        second = self.command('event-create', *controls, '-', input=json.dumps(content, ensure_ascii=False))
        self.assertEqual(first['event']['content'], content)
        self.assertEqual(second['event']['content'], content)
        self.assertNotEqual(first['event']['event_id'], second['event']['event_id'])
        self.assertTrue(first['event']['created_time'])
        selected = self.command('events-query', '--branch-id', 'main', '--object-ids', 'cli-memory',
                                '--fields', 'event_id', 'content', '--no-include-total',
                                '--filter', 'event_type=role_memory')
        self.assertIsNone(selected['total'])
        self.assertEqual(len(selected['items']), 2)
        self.assertEqual(selected['items'][0]['content'], content)

    def test_record_patch_relation_auto_id_filters_and_batch(self):
        self.command('node-begin', '--node-id', 'root', '--node-type', 'root', '--branch-id', 'main')
        self.command('record-create', '--entity', 'object', '--object-id', 'cli-object',
                     '--object-type', 'truth', '--object-key', 'example', '--name', '初始名称')
        updated = self.command('record-update', '--entity', 'object', '--record-id', 'cli-object', '--name', '更新名称')
        self.assertEqual(updated['name'], '更新名称')
        relation = self.command('relation-create', '--relation-type', 'reference', '--key-type', 'object',
                                '--key-id', 'cli-object', '--target-node-id', 'root')
        self.assertTrue(relation['relation_id'].startswith('relation-'))
        selected = self.command('record-list', '--entity', 'relation', '--filter', 'relation_type=reference')
        self.assertEqual(selected['total'], 1)
        commands = [{'operation': 'record.get', 'params': {'entity': 'object', 'record_id': 'cli-object'}},
                    {'operation': 'record.get', 'params': {'entity': 'relation', 'record_id': relation['relation_id']}}]
        path = self.root / 'commands.json'
        path.write_text(json.dumps(commands), encoding='utf-8')
        result = self.command('batch', '--commands-file', str(path))
        self.assertEqual(result[0]['name'], '更新名称')
        self.assertEqual(result[1]['relation_id'], relation['relation_id'])
