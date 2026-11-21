"""Normal metadata discovery, lifecycle, and read/write boundaries."""
from creative_common import CreativeCase
from script.workflow.cli.api import Application
from script.cli.main import execute


class Management(CreativeCase):
    def test_story_discovery_info_and_archive_restore(self):
        writer=Application(data_root=self.root/'library',resources=self.app.resources)
        content={'settings':{'background':{'place':'TEST'}},'raw_user_messages':[{'text':'SIMULATION','source':'simulation'}]}
        try:
            initialized=execute(writer,{'operation':'story_init','params':{'story_id':'managed-story','title':'MANAGED','environment':'debug','content':content}})
            self.assertTrue(initialized['ok'],initialized)
            listing=execute(writer,{'operation':'story.list','params':{'environment':'debug'}})
            self.assertTrue(listing['ok'],listing);self.assertEqual(listing['data'][0]['title'],'MANAGED')
            self.assertNotIn('literary_text',str(listing['data']))
            reader=Application(initialized['data']['config_path'],resources=self.app.resources)
            try:
                archived=execute(reader,{'operation':'story.state','params':{'lifecycle':'archived'}})
                self.assertTrue(archived['ok'],archived)
                request={'operation':'scene_next','params':{'branch_id':'main','mode':'normal','content':{'raw_user_messages':[{'text':'继续','source':'simulation'}]}}}
                self.assertEqual(execute(reader,request)['error']['code'],'STORY_ARCHIVED')
                self.assertTrue(execute(reader,{'operation':'story.info','params':{}})['ok'])
                self.assertTrue(execute(reader,{'operation':'story.state','params':{'lifecycle':'active'}})['ok'])
                self.assertTrue(execute(reader,request)['ok'])
            finally:reader.close()
        finally:writer.close()

    def test_branch_completed_is_not_no_head_and_can_reopen(self):
        self.root_node();node=self.ordinary()
        self.call('branch.state',branch_id='main',lifecycle='completed')
        listing=self.call('branch.list')
        self.assertEqual(listing[0]['lifecycle'],'completed');self.assertEqual(listing[0]['head']['node_id'],node)
        response=execute(self.app,{'operation':'scene_next','params':{'branch_id':'main','mode':'normal','content':{'raw_user_messages':[{'text':'继续','source':'simulation'}]}}})
        self.assertEqual(response['error']['code'],'BRANCH_CLOSED')
        self.call('branch.state',branch_id='main',lifecycle='open')
        self.assertNotEqual(self.open()['node_id'],node)
