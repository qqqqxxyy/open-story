"""First-use defaults stay local and materialize the active writing contract."""
from pathlib import Path
from dataclasses import replace
import json
import subprocess
import sys
import unittest
from common import REPO, FunctionalCase
from script.initialize import initialize, status, read_preferences
from script.workflow.cli.api import Application


class Setup(FunctionalCase):
    def setUp(self):
        super().setUp()
        self.skill = self.root/'skill'
        (self.skill/'author').mkdir(parents=True)
        source = REPO/'author/writing-contract.template.md'
        (self.skill/'author/writing-contract.template.md').write_text(source.read_text(encoding='utf8'), encoding='utf8')

    def test_first_use_status_then_materializes_user_choices_in_private_contract(self):
        self.assertEqual(status(self.skill)['initialized'], False)
        profile = {'protagonist': {'name': '示例用户主角', 'identity': '旅行者'},
                   'narration': {'person': 'third', 'viewpoint': 'limited'},
                   'raw_user_messages': [{'text': '第三人称，跟随主人公。', 'source': 'simulation'}]}
        done = initialize(self.skill, profile)
        self.assertTrue(done['initialized'])
        contract = self.skill/'author/writing-contract.md'
        self.assertIn('示例用户主角', contract.read_text(encoding='utf8'))
        self.assertIn('"person": "third"', contract.read_text(encoding='utf8'))
        self.assertEqual(read_preferences(self.skill), profile)
        ignored = subprocess.run(['git', 'check-ignore', '--no-index', 'author/writing-contract.md',
                                  '.openstory/preferences.json'], cwd=REPO, capture_output=True,
                                 text=True, check=True).stdout.splitlines()
        self.assertEqual(set(ignored), {'author/writing-contract.md', '.openstory/preferences.json'})

    def test_no_fixed_defaults_and_reconfiguration_preserve_other_local_rules(self):
        initialize(self.skill, {'protagonist': None, 'narration': None})
        path = self.skill/'author/writing-contract.md'
        path.write_text(path.read_text(encoding='utf8')+'\nLOCAL_CUSTOM_RULE\n', encoding='utf8')
        profile = {'protagonist': {'name': '示例主角'}, 'narration': {'person': 'first'}}
        initialize(self.skill, profile)
        self.assertIn('LOCAL_CUSTOM_RULE', path.read_text(encoding='utf8'))
        self.assertIn('"person": "first"', path.read_text(encoding='utf8'))
        before = path.read_bytes()
        initialize(self.skill, profile)
        self.assertEqual(path.read_bytes(), before)

    def test_cli_status_restore_and_user_selected_defaults_in_new_story(self):
        profile = {'protagonist': {'name': '示例主角'}, 'narration': {'person': 'first', 'viewpoint': 'limited'}}
        initialize(self.skill, profile)
        (self.skill/'author/writing-contract.md').unlink()
        command = [sys.executable, '-B', '-X', 'utf8', str(REPO/'script/initialize.py'), '--root', str(self.skill)]
        result = subprocess.run(command+['--status'], capture_output=True, text=True, encoding='utf8', check=True)
        current = json.loads(result.stdout)
        self.assertFalse(current['needs_preferences'])
        self.assertTrue(current['needs_contract'])
        restored = subprocess.run(command+['--restore'], capture_output=True, text=True, encoding='utf8', check=True)
        self.assertTrue(json.loads(restored.stdout)['initialized'])
        self.app.close()
        self.app = Application(data_root=self.root/'stories',
                               resources=replace(self.app.resources, project_root=self.skill))
        result = self.call('story_init', story_id='configured-world', title='TEST_TITLE',
                           content={'settings': {'background': 'TEST_WORLD'},
                                    'raw_user_messages': [{'text': 'TEST_START', 'source': 'simulation'}]})
        self.assertEqual(result['settings']['protagonist'], profile['protagonist'])
        self.assertEqual(result['settings']['narration'], profile['narration'])
        explicit = self.call('story_init', story_id='explicit-world', title='TEST_EXPLICIT',
                           content={'settings': {'protagonist': {'name': '故事专用主角'}, 'narration': {'person': 'third'}},
                                    'raw_user_messages': [{'text': 'TEST_START', 'source': 'simulation'}]})
        self.assertEqual(explicit['settings']['protagonist']['name'], '故事专用主角')
        self.assertEqual(explicit['settings']['narration']['person'], 'third')
