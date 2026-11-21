"""Normal API discovery and help-driven invocation, using isolated temporary stories."""
from common import FunctionalCase, REPO
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from script.cli.bootstrap import bootstrap
from script.cli.arguments import parse_request
from script.cli.main import execute
from script.workflow.cli.api import Application


class Help(FunctionalCase):
    def help(self,*args):
        result=subprocess.run([sys.executable,'-B','-X','utf8',str(REPO/'script/cli/main.py'),*args],
                              capture_output=True,text=True,encoding='utf8',check=True)
        self.assertEqual(result.stderr,'')
        return result.stdout

    def test_real_overview_and_target_help_without_database_or_payload_reads(self):
        overview=self.help('--help')
        self.assertIn('开启普通幕或交互幕',overview)
        self.assertIn('召回对象在目标分支世界线上的event',overview)
        missing=self.root/'not-created/story.json'
        target=self.help('object-events','--config',str(missing),'--help')
        self.assertIn('默认=100',target)
        self.assertIn('total',target)
        self.assertIn('返回：',target)
        self.assertIn('分支前驱链',target)
        self.assertNotIn('raw_user_messages',target)
        self.assertFalse(missing.parent.exists())
        init_root=self.root/'not-created-init'
        init=self.help('story-init','--data-root',str(init_root),'--content-file',str(self.root/'absent.json'),'--help')
        for token in ('JSON内容契约','raw_user_messages','settings','config_path','already_initialized'):
            self.assertIn(token,init)
        self.assertFalse(init_root.exists())
        scene_help=self.help('scene-next','--help')
        self.assertIn('history_node_id',scene_help)
        self.assertIn('raw_input_event_ids',scene_help)
        self.assertIn('[可用]',scene_help)

    def test_all_registered_help_and_examples_resolve_public_contracts(self):
        resources=self.app.resources
        self.assertEqual(set(resources.schemas['workflow']['definitions']),{'event_owner','deletion_context','range_deletion_context','workflow_objects','capsule_config','reading_config','prose_cursor'})
        for entry in resources.operations.values():
            with self.subTest(operation=entry['operation']):
                self.assertTrue(entry['input_schema']['$ref'].startswith('urn:open-story:agent#'))
                self.assertTrue(entry['output_schema']['$ref'].startswith('urn:open-story:agent#'))
                output=io.StringIO()
                with redirect_stdout(output):
                    with self.assertRaises(SystemExit) as stopped:
                        parse_request([entry['cli_name'],'--help'],resources)
                self.assertEqual(stopped.exception.code,0)
                self.assertIn('返回：',output.getvalue())
                self.assertIn(entry['help']['summary'],output.getvalue())
                example=entry['help']['examples'][0]
                arguments=list(example['arguments'])
                if 'content' in example:
                    payload=self.root/(entry['cli_name']+'.json')
                    payload.write_text(json.dumps(example['content'],ensure_ascii=False),encoding='utf8')
                    file_index=next(i for i,arg in enumerate(arguments) if arg.endswith('-file'))+1
                    arguments[file_index]=str(payload)
                request,_,_,_,_=parse_request([entry['cli_name'],*arguments],resources)
                resources.validator.validate(request['params'],entry['input_schema'])

    def test_public_control_defaults_drive_help_and_actual_query(self):
        self.root_node();self.scene(publish=False)
        for index in range(3):self.event(node='scene-1',event_id='memory-'+str(index))
        conf=self.root/'conf';shutil.copytree(REPO/'script/conf',conf)
        path=conf/'schemas/schema_for_agent.json'
        schema=json.loads(path.read_text(encoding='utf8'))
        props=schema['definitions']['operation_object_events']['properties']
        props['limit']['default']=2
        props['include_total']['default']=False
        schema['definitions']['operation_object_events']['required'].append('state')
        path.write_text(json.dumps(schema),encoding='utf8')
        resources=bootstrap(conf_path=conf,project_root=self.root)
        app=Application(self.config,resources=resources)
        try:
            output=io.StringIO()
            with redirect_stdout(output):
                with self.assertRaises(SystemExit):parse_request(['object-events','--help'],resources)
            self.assertIn('默认=2',output.getvalue())
            self.assertIn('默认=false',output.getvalue())
            self.assertIn('必填；枚举',output.getvalue())
            response=execute(app,{'operation':'object.events','params':{'branch_id':'main','object_id':'memory-player','state':'active'}})
            self.assertTrue(response['ok'],response)
            self.assertEqual(len(response['data']['items']),2)
            self.assertIsNone(response['data']['total'])
            self.assertEqual(response['data']['next_offset'],2)
        finally:
            app.close();bootstrap()

    def test_help_example_initialization_preserves_content_and_public_result(self):
        resources=self.app.resources
        entry=resources.operations['story_init']
        example=entry['help']['examples'][0]
        content=self.root/'opening.json'
        content.write_text(json.dumps(example['content'],ensure_ascii=False),encoding='utf8')
        arguments=list(example['arguments'])
        arguments[arguments.index('--content-file')+1]=str(content)
        arguments.extend(['--data-root',str(self.root/'example-stories')])
        request,_,data_root,_,_=parse_request(['story-init',*arguments],resources)
        app=Application(data_root=data_root,resources=resources)
        try:
            result=execute(app,request)
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['data']['environment'],'debug')
            resources.validator.validate(result['data'],entry['output_schema'])
            reader=Application(result['data']['config_path'],resources=resources)
            try:
                stored=execute(reader,{'operation':'node.events','params':{'branch_id':'main','node_id':'node-root','event_type':'user_input'}})
                self.assertTrue(stored['ok'],stored)
                self.assertEqual(stored['data']['items'][0]['content']['text'],example['content']['raw_user_messages'][0]['text'])
            finally:reader.close()
        finally:app.close()

    def test_programmatic_examples_match_current_public_contracts(self):
        resources=self.app.resources
        paths=list((REPO/'examples/programmatic').glob('*.json'))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.name):
                request=json.loads(path.read_text(encoding='utf8'))
                resources.validator.validate(request,resources.schemas['agent']['definitions']['request'])
                resources.validator.validate(request['params'],resources.operations[request['operation']]['input_schema'])

    def test_real_help_does_not_lock_or_rotate_existing_logs(self):
        conf=self.root/'help-conf';shutil.copytree(REPO/'script/conf',conf)
        logs=self.root/'default_logs';logs.mkdir()
        filename=logs/'runtime.log'
        original='{"time":"2000-01-01T00:00:00+00:00","level":"info","message":"OLD_LOG"}\n'
        filename.write_text(original,encoding='utf8')
        settings=json.loads((conf/'runtime.json').read_text(encoding='utf8'))
        settings['logging']['default_path']='default_logs'
        (conf/'runtime.json').write_text(json.dumps(settings),encoding='utf8')
        script=self.root/'query_help.py'
        script.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(REPO))+')\n'
            'from script.cli import main as cli\n'
            'original=cli.bootstrap\n'
            'cli.bootstrap=lambda **options: original(conf_path='+repr(str(conf))+',project_root='+repr(str(self.root))+',**options)\n'
            'cli.main(["scene-next","--help"])\n',encoding='utf8')
        run=subprocess.run([sys.executable,'-B','-X','utf8',str(script)],capture_output=True,text=True,encoding='utf8',check=True)
        self.assertEqual(run.stderr,'')
        self.assertIn('不实例化日志',run.stdout)
        self.assertEqual(filename.read_text(encoding='utf8'),original)
        self.assertEqual({file.name for file in logs.iterdir()},{'runtime.log'})


    def test_help_stdin_pipeline_submits_unicode_author_content_in_one_call(self):
        self.root_node();scene=self.call('scene_next',branch_id='main',mode='normal',content={'raw_user_messages':[{'text':'原始输入','source':'simulation'}]})
        node=scene['node_id']
        packet=self.call('director.save',node_id=node,content={'interpreted_intent':'TEST_INTENT'})
        from copy import deepcopy
        from script.cli.help import command_details
        entry=deepcopy(self.app.resources.operations['author.save'])
        example=entry['help']['examples'][0]
        example['arguments']=[str(self.config) if value=='<故事配置>' else node if value=='<node_id>' else packet['packet_event_id'] if value=='<packet_event_id>' else value for value in example['arguments']]
        example['content']={'literary_text':'中文“引号”\n两处  空格与换行。','feedback':{'note':'反馈是对象','details':['甲','乙']}}
        help_text=command_details(self.app.resources,entry)
        start=help_text.index('$OutputEncoding =')
        end=help_text.index('\n\n查询本help',start)
        pipeline=help_text[start:end]
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',pipeline],capture_output=True,text=True,encoding='utf8',check=True)
        self.assertEqual(result.stderr,'')
        saved=json.loads(result.stdout);self.assertTrue(saved['ok'],saved)
        received=self.call('author.read',node_id=node,packet_event_id=saved['data']['packet_event_id'])
        self.assertEqual(received['literary_text'],example['content']['literary_text'])
        self.assertEqual(received['feedback'],example['content']['feedback'])


    def test_revision_and_maintenance_help_exposes_shared_contract_and_conditions(self):
        from script.cli.help import command_details
        expected={'scene.prepare':['--revision-kind','base_author_packet_event_id','条件约束','minor','major','request_id'],
                  'scene.submit':['attempt_id','maintenance','next_job','awaiting_feedback'],
                  'scene.maintenance':['job_id','semantic_pending','capsule_pending','adopted','scope','events','capsules'],
                  'scene.accept':['--request-id','--author-packet-event-id','maintenance'],
                  'dialogue.close':['final_literary_text']}
        for operation,tokens in expected.items():
            text=command_details(self.app.resources,self.app.resources.operations[operation])
            for token in tokens:self.assertIn(token,text,operation)
        request,_,_,_,_=parse_request(['scene-prepare','--config',str(self.config),'--action','resume','--node-id','N'],self.app.resources)
        self.app.resources.validator.validate(request['params'],self.app.resources.operations['scene.prepare']['input_schema'])
