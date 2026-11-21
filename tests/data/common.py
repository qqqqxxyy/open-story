from pathlib import Path
from dataclasses import replace
import json
import sys
import tempfile
import unittest
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from script.cli.bootstrap import bootstrap
bootstrap()
from script.workflow.cli.api import Application
from script.cli.main import execute
from script.util.logging import StoryLogger

class FunctionalCase(unittest.TestCase):
    backend='sqlite'
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='openstory-data-functional-')
        self.root=Path(self.temp.name);self.config=self.root/'config.json'
        self.config.write_text(json.dumps({'skill_version':6,'database_id':'functional','backend':self.backend,
            'location':'db.sqlite3' if self.backend=='sqlite' else 'file-store'}),encoding='utf8')
        resources=bootstrap()
        source=resources.logger
        logger=StoryLogger(self.root/'story-data/default_logs',source.level,source.filename,
                           source.lock_timeout_seconds,source.rotation_days)
        self.app=Application(self.config,resources=replace(resources,logger=logger))
    def tearDown(self):self.app.close();self.temp.cleanup();bootstrap()
    def call(self,operation,**params):
        if operation in {'node.begin','event.create','node.revise','node.publish','node.read','node.cancel','node.delete_leaf','event.cancel','node.events','object.events'}:
            params.setdefault('branch_id','main')
        result=execute(self.app,{'operation':operation,'params':params})
        self.assertTrue(result['ok'],result)
        return result['data']
    def root_node(self):
        self.call('node.begin',node_id='root',node_type='root')
        self.call('node.publish',node_id='root')
    def event(self,node='root',event_id='memory-1',object_id='memory-player',**options):
        return self.call('event.create',node_id=node,
            object={'object_id':object_id,'object_type':'role_memory','object_key':object_id,'name':'示例主角记忆'},
            event={'event_id':event_id,'event_type':'role_memory','type_name':'player','content':{'claim':'听见了铃声','自由栏目':{'颜色':'蓝'}}},**options)
    def scene(self,node='scene-1',parent='root',publish=True,branch='main'):
        self.call('node.begin',node_id=node,predecessor_id=parent,branch_id=branch)
        self.call('event.create',node_id=node,branch_id=branch,
            object={'object_id':'prose','object_type':'author_reply','object_key':'prose','name':'正文'},
            event={'event_id':'prose-'+node,'event_type':'author_reply','type_name':'prose','content':{'literary_text':'铃声响起，他停下脚步。'}},select_as='narrative')
        self.call('event.create',node_id=node,branch_id=branch,
            object={'object_id':'summary','object_type':'scene_summary','object_key':'summary','name':'摘要'},
            event={'event_id':'summary-'+node,'event_type':'scene_summary','type_name':'summary','content':{'summary':'听见铃声'}},select_as='summary')
        if publish:self.call('node.publish',node_id=node,branch_id=branch)
