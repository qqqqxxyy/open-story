"""Normal integration cases for configuration extension, logs and composed SQL."""
from common import FunctionalCase, REPO
from contextlib import redirect_stderr, redirect_stdout
import ast
import importlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from script.cli.bootstrap import bootstrap
from script.cli.arguments import parse_request
from script.cli.main import execute
from script.util.logging import StoryLogger
from script.util.runtime import using
from script.workflow.cli.api import Application


class Runtime(FunctionalCase):
    def test_registered_new_command_with_controls_json_and_temporary_handler(self):
        conf=self.root/'conf'
        shutil.copytree(REPO/'script/conf',conf)
        catalog=json.loads((conf/'operations.json').read_text(encoding='utf8'))
        catalog['operations'].append({
            'operation':'functional.probe','cli_name':'functional-probe',
            'storage_mode':'existing',
            'handler':'script.workflow.pipeline.handlers.functional_probe:execute',
            'input_schema':{'type':'object','properties':{'label':{'type':'string'},'content':{}},
                            'required':['label','content'],'additionalProperties':False},
            'output_schema':{'type':'object','required':['label','content','counts']},
            'help':{'summary':'TEST_PROBE_SUMMARY','notes':['TEST_PROBE_NOTE'],'examples':[]},
            'containers':[],
            'bindings':[{'flag':'--label','path':['label'],'kind':'value','required':True,'schema':{'type':'string'}},
                        {'flag':'--content-file','path':['content'],'kind':'json_file','required':True,'schema':{}}],
        })
        (conf/'operations.json').write_text(json.dumps(catalog),encoding='utf8')
        module_folder=self.root/'handlers';module_folder.mkdir()
        (module_folder/'functional_probe.py').write_text(
            "def execute(context, params):\n    return {**params, 'counts':context.repository.info()['counts']}\n",encoding='utf8')
        import script.workflow.pipeline.handlers as handlers
        handlers.__path__.append(str(module_folder))
        importlib.invalidate_caches()
        payload={'自由栏目':{'原文':'保留  空格\n换行'}}
        content=self.root/'content.json';content.write_text(json.dumps(payload),encoding='utf8')
        resources=bootstrap(conf_path=conf,project_root=self.root)
        app=Application(self.config,resources=resources)
        try:
            request,config,_,_,_=parse_request(['functional-probe','--config',str(self.config),'--label','TEST_LABEL',
                                            '--content-file',str(content)],resources)
            response=execute(app,request)
            self.assertTrue(response['ok'],response)
            self.assertEqual(response['data']['content'],payload)
            self.assertEqual(response['data']['label'],'TEST_LABEL')
            output=io.StringIO()
            with redirect_stdout(output):
                with self.assertRaises(SystemExit) as stopped:
                    parse_request(['functional-probe','--help'],resources)
            self.assertEqual(stopped.exception.code,0)
            for token in ('TEST_PROBE_SUMMARY','TEST_PROBE_NOTE','counts','返回：'):
                self.assertIn(token,output.getvalue())
            self.assertEqual(response['data']['counts'],{'node':0,'object':0,'event':0,'relation':0})
        finally:
            app.close()
            handlers.__path__.remove(str(module_folder))
            sys.modules.pop('script.workflow.pipeline.handlers.functional_probe',None)
            bootstrap()

    def test_central_logs_levels_targets_duration_and_result(self):
        default=self.root/'default_logs'
        logger=StoryLogger(default)
        logger.debug('hidden');logger.info('normal');logger.warn('attention');logger.error('failure')
        records=[json.loads(line) for line in (default/'runtime.log').read_text(encoding='utf8').splitlines()]
        self.assertEqual([r['level'] for r in records],['info','warn','error'])
        logger.level='debug';logger.debug('visible')
        self.assertEqual(json.loads((default/'runtime.log').read_text(encoding='utf8').splitlines()[-1])['level'],'debug')
        self.root_node()
        self.call('branch.read',branch_id='main')
        log=self.app.logger.default_path/'runtime.log'
        records=[json.loads(line) for line in log.read_text(encoding='utf8').splitlines()]
        pair=[r for r in records if r['operation']=='branch.read']
        self.assertEqual([r['message'] for r in pair],['operation.started','operation.completed'])
        self.assertEqual(pair[0]['invocation_id'],pair[1]['invocation_id'])
        self.assertEqual(pair[0]['call_id'],pair[1]['call_id'])
        self.assertEqual(pair[0]['branch_id'],'main')
        self.assertEqual(pair[0]['params']['branch_id'],'main')
        self.assertEqual(pair[1]['result']['head']['node_id'],'root')
        self.assertGreaterEqual(pair[1]['duration_ms'],0)
        self.assertFalse((self.config.parent/'logs').exists())

    def test_configured_rotation_on_instantiation_and_current_window(self):
        from datetime import datetime,timedelta,timezone
        conf=self.root/'rotation-conf';shutil.copytree(REPO/'script/conf',conf)
        path=conf/'runtime.json';settings=json.loads(path.read_text(encoding='utf8'))
        self.assertEqual(settings['logging']['rotation_days'],7)
        settings['logging']['rotation_days']=2
        settings['logging']['default_path']='central-logs'
        path.write_text(json.dumps(settings),encoding='utf8')
        directory=self.root/'central-logs';directory.mkdir()
        filename=directory/'runtime.log'
        old={'time':(datetime.now(timezone.utc)-timedelta(days=3)).isoformat(),'level':'info','message':'old'}
        filename.write_text(json.dumps(old)+'\n',encoding='utf8')
        resources=bootstrap(conf_path=conf,project_root=self.root)
        app=Application(self.config,resources=resources)
        try:
            response=execute(app,{'operation':'database.info','params':{}})
            self.assertTrue(response['ok'],response)
            archives=list(directory.glob('runtime.*.log'))
            self.assertEqual(len(archives),1)
            self.assertEqual(json.loads(archives[0].read_text(encoding='utf8'))['message'],'old')
            self.assertEqual(json.loads(filename.read_text(encoding='utf8').splitlines()[0])['message'],'operation.started')
            StoryLogger(directory,rotation_days=2)
            self.assertEqual(len(list(directory.glob('runtime.*.log'))),1)
        finally:
            app.close();bootstrap()

    def test_same_invocation_nested_calls_and_failure_stage(self):
        self.root_node()
        self.app.logger.level='debug'
        self.call('batch',commands=[{'operation':'branch.read','params':{'branch_id':'main'}},
                                  {'operation':'database.info','params':{}}])
        response=execute(self.app,{'operation':'branch.read','params':{'branch_id':'missing-branch'}})
        self.assertFalse(response['ok'])
        records=[json.loads(line) for line in (self.app.logger.default_path/'runtime.log').read_text(encoding='utf8').splitlines()]
        self.assertEqual({r['invocation_id'] for r in records},{self.app.invocation_id})
        starts=[r for r in records if r['message']=='operation.started']
        batch=next(r for r in starts if r['operation']=='batch')
        children=[r for r in starts if r.get('parent_call_id')==batch['call_id']]
        self.assertEqual([r['operation'] for r in children],['branch.read','database.info'])
        self.assertEqual(len({r['call_id'] for r in starts}),len(starts))
        self.assertTrue(any(r['message']=='transaction.committed' for r in records))
        self.assertTrue(any(r['message']=='handler.started' and r.get('function') for r in records))
        failed=next(r for r in records if r['message']=='operation.failed')
        self.assertEqual(failed['phase'],'handler_execution')
        self.assertEqual(failed['branch_id'],'missing-branch')
        self.assertTrue(failed['code'])
        self.assertGreaterEqual(failed['duration_ms'],0)

    def test_initialization_story_tags_and_early_configuration_failure(self):
        request={'operation':'story_init','params':{'story_id':'logged-story','title':'SIMULATION',
            'content':{'settings':{'background':{'place':'test'}},
                       'raw_user_messages':[{'text':'SIMULATION','source':'simulation'}]}}}
        writer=Application(data_root=self.root/'stories',resources=self.app.resources)
        try:
            response=execute(writer,request);self.assertTrue(response['ok'],response)
            reader=Application(response['data']['config_path'],resources=self.app.resources)
            try:
                read=execute(reader,{'operation':'branch.read','params':{'branch_id':'main'}})
                self.assertTrue(read['ok'],read)
            finally:reader.close()
            # Documented initialization precondition rejects --config before dispatch.
            failure=execute(self.app,request);self.assertFalse(failure['ok'])
            records=[json.loads(line) for line in (writer.logger.default_path/'runtime.log').read_text(encoding='utf8').splitlines()]
            completed=[r for r in records if r['message']=='operation.completed']
            self.assertTrue(all(r.get('database_id')=='logged-story' and 'story_id' not in r for r in completed))
            self.assertEqual(completed[-1]['branch_id'],'main')
            failed=next(r for r in records if r['message']=='operation.failed')
            self.assertEqual(failed['phase'],'configuration_validation')
            self.assertFalse((self.root/'stories/online/logged-story/logs').exists())
            self.assertTrue((self.root/'stories/online/logged-story/story.sqlite3').exists())
        finally:writer.close()

    def test_composed_recall_and_reference_queries_keep_constant_statement_counts(self):
        self.root_node()
        self.scene(publish=False)
        self.event(node='scene-1',event_id='memory-0')
        db=self.app.repository._store.db
        def recall():
            statements=[];db.set_trace_callback(statements.append)
            try:
                result=self.call('object.events',object_id='memory-player',fields=['event_id','content'],include_total=False)
            finally: db.set_trace_callback(None)
            return result,[s for s in statements if s.lstrip().upper().startswith(('SELECT','WITH'))]
        one,first=recall()
        for index in range(1,9):self.event(node='scene-1',event_id='memory-'+str(index))
        many,second=recall()
        self.assertEqual(len(one['items']),1)
        self.assertEqual(len(many['items']),9)
        self.assertEqual(len(first),len(second))
        self.assertTrue(any('JOIN' in sql.upper() and 'WITH RECURSIVE' in sql.upper() for sql in second))
        statements=[];db.set_trace_callback(statements.append)
        try:
            self.app.repository._store.references(event_ids=[e['event_id'] for e in many['items']])
        finally:db.set_trace_callback(None)
        self.assertEqual(len(statements),2)

    def test_declarative_conf_dependency_direction_and_central_error_codes(self):
        ranks={'conf':0,'util':1,'data':2,'workflow':3,'cli':4}
        # conf contains no executable Python. Upper layers supply loaded resources to lower layers.
        self.assertFalse(list((REPO/'script/conf').rglob('*.py')))
        for layer in ranks:
            for path in (REPO/'script'/layer).rglob('*.py'):
                tree=ast.parse(path.read_text(encoding='utf8'))
                from collections import Counter
                for cls in (node for node in tree.body if isinstance(node,ast.ClassDef)):
                    names=[node.name for node in cls.body if isinstance(node,ast.FunctionDef)]
                    self.assertTrue(all(count==1 for count in Counter(names).values()),path)
                for node in ast.walk(tree):
                    names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) and node.level==0 else []
                    for name in names:
                        parts=name.split('.')
                        if len(parts)>1 and parts[0]=='script' and parts[1] in ranks:
                            self.assertLessEqual(ranks[parts[1]],ranks[layer],(path,name))
        resources=self.app.resources
        for path in (REPO/'script').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('ContractError','DataError') and node.args and isinstance(node.args[0],ast.Constant):
                    self.assertIn(node.args[0].value,resources.errors,(path,node.args[0].value))
        self.assertGreaterEqual(len(resources.operations),45)
        self.assertFalse((REPO/'script/schema/loader.py').exists())

    def test_source_mapping_query_is_composed(self):
        self.root_node();self.scene(publish=False)
        self.event(node='scene-1',event_id='source-memory-1')
        db=self.app.repository._store.db
        counts=[]
        for round in range(2):
            statements=[];db.set_trace_callback(statements.append)
            try:
                rows=self.app.repository.source_records('scene-1',event_types=['role_memory'])
            finally:db.set_trace_callback(None)
            counts.append(len(statements))
            self.assertTrue(all(row['node_id']=='scene-1' for row in rows))
            if not round:
                for index in range(2,9):self.event(node='scene-1',event_id='source-memory-'+str(index))
        self.assertEqual(counts,[1,1])


    def test_unified_version_policy_and_v6_transaction_marker(self):
        self.assertEqual(self.app.resources.settings['skill_version'],7)
        from script.util.versioning import version_policy, validate_version
        from script.util.errors import ContractError
        for value in (6,7):self.assertEqual(validate_version(value),value)
        for value in (5,8,0,-1,True,'7',None):
            with self.assertRaises(ContractError) as failure:validate_version(value)
            self.assertEqual(failure.exception.code,'VERSION_UNSUPPORTED')
        future=version_policy({**self.app.resources.settings,'skill_version':8})
        self.assertEqual(validate_version(8,future),8)
        with self.assertRaises(ContractError):validate_version(9,future)
        store=self.app.repository._store
        store.db.execute('PRAGMA user_version=6')
        before=self.config.read_bytes()
        self.assertEqual(self.call('database.info')['counts']['node'],0)
        self.assertEqual(store.skill_version,6)
        with store.transaction():pass
        self.assertEqual(store.skill_version,6)
        try:
            with store.transaction():
                self.call('object.ensure',object_id='rolled-back',object_type='test',object_key='rollback',name='test')
                raise ValueError('rollback')
        except ValueError:pass
        self.assertEqual(store.skill_version,6)
        self.assertIsNone(store.get('object','rolled-back'))
        self.call('object.ensure',object_id='committed',object_type='test',object_key='commit',name='test')
        self.assertEqual(store.skill_version,7)
        self.assertEqual(self.app.repository.identity()['skill_version'],7)
        self.assertEqual(self.config.read_bytes(),before)

    def test_future_database_rejected_before_business_decode(self):
        from script.data.api import connect
        from script.util.errors import ContractError
        store=self.app.repository._store
        store.db.execute('PRAGMA user_version=8')
        with self.assertRaises(ContractError) as failure:connect(self.config)
        self.assertEqual(failure.exception.code,'VERSION_UNSUPPORTED')
        self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0],8)
