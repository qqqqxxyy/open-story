"""Normal append, targeted replacement/cancellation and scoped creative recall."""
from copy import deepcopy
from dataclasses import replace
from creative_common import CreativeCase
from script.cli.arguments import parse_request
from script.cli.main import execute


class EventActions(CreativeCase):
    def save(self, node, text=None, action='append', targets=None, **extra):
        params=dict(node_id=node,kind='role_memory',key='player',event_action=action,**extra)
        if text is not None:params['content']={'character_id':'player','claim':text}
        if targets is not None:params['target_event_ids']=targets
        return self.call('business.save',**params)['event']

    def claims(self,node,**extra):
        return [r['event']['content']['claim'] for r in self.call('business.read',node_id=node,kind='role_memory',**extra)['current']]

    def test_targeted_replace_cancel_and_append_preserve_history(self):
        self.root_node();node=self.open()['node_id']
        a=self.save(node,'MEMORY_A');b=self.save(node,'MEMORY_B');c=self.save(node,'MEMORY_C')
        replacement=self.save(node,'MEMORY_AB','replace',[a['event_id'],b['event_id']])
        self.assertEqual(self.claims(node),['MEMORY_C','MEMORY_AB'])
        cancelled=self.save(node,action='cancel',targets=[c['event_id']])
        self.save(node,'MEMORY_D')
        self.assertEqual(self.claims(node),['MEMORY_AB','MEMORY_D'])
        data=self.call('business.read',node_id=node,kind='role_memory',include_history=True)
        self.assertEqual(len(data['history']),6)
        self.assertTrue(all(r['event']['state']=='active' for r in data['history']))
        self.assertEqual(cancelled['event_action'],'cancel')
        self.assertEqual(replacement['content']['_control']['target_event_ids'],[a['event_id'],b['event_id']])
        links=self.call('record.list',entity='relation',filters={'relation_type':'event_action_target','key_id':replacement['event_id']})
        self.assertEqual({r['target_event_id'] for r in links['items']},{a['event_id'],b['event_id']})

    def test_branch_replacement_does_not_change_shared_history_or_other_branch(self):
        self.root_node()
        original=self.save('root','SHARED_MEMORY',branch_id='main')
        main=self.open()['node_id']
        self.save(main,'MAIN_MEMORY','replace',[original['event_id']])
        self.director(main);self.call('author.save',node_id=main,content={'literary_text':'MAIN_PROSE'});self.finish(main)
        self.call('branch.fork',branch_id='alternate',from_node_id='root',node_id='alt-draft')
        alt=self.call('scene_next',branch_id='alternate',mode='normal',content={'raw_user_messages':[{'text':'ALT_INPUT','source':'simulation'}]})['node_id']
        self.assertEqual(self.claims('root',branch_id='main'),['SHARED_MEMORY'])
        self.assertEqual(self.claims(main),['MAIN_MEMORY'])
        self.assertEqual(self.claims(alt),['SHARED_MEMORY'])
        next_main=self.open()['node_id']
        recalled=self.call('scene.context',view='full',node_id=next_main)
        self.assertEqual([r['event']['content']['claim'] for r in recalled['projection']['role_memory']],['MAIN_MEMORY'])
        self.assertNotIn(original['event_id'],{r['event']['event_id'] for r in recalled['sources']})

    def test_archive_target_actions_and_retry(self):
        self.root_node();node=self.open()['node_id']
        a=self.save(node,'ORIGINAL')
        self.director(node);self.call('author.save',node_id=node,content={'literary_text':'ARCHIVE_PROSE'})
        entries=[{'kind':'role_memory','key':'player','event_action':'replace','target_event_ids':[a['event_id']],
                  'content':{'character_id':'player','claim':'ARCHIVED_REPLACEMENT'}},
                 {'kind':'role_memory','key':'player','content':{'character_id':'player','claim':'APPENDED'}}]
        self.finish(node,entries);self.finish(node,entries)
        self.assertEqual(self.claims(node),['ARCHIVED_REPLACEMENT','APPENDED'])
        self.assertEqual(len(self.call('business.read',node_id=node,kind='role_memory',include_history=True)['history']),3)

    def test_cli_cancel_without_fake_content_and_explicit_history_read(self):
        self.root_node();node=self.open()['node_id'];a=self.save(node,'MEMORY_A')
        request,_,_,_,_=parse_request(['business-save','--config',str(self.config),'--node-id',node,'--kind','role_memory',
                                    '--key','player','--event-action','cancel','--target-event-ids',a['event_id']])
        result=execute(self.app,request);self.assertTrue(result['ok'],result)
        self.assertEqual(self.claims(node),[])
        historical=self.call('context.read',node_id=node,event_ids=[a['event_id']])
        self.assertEqual(historical['sources'][0]['event']['event_id'],a['event_id'])

    def test_old_reply_pairing_is_preserved(self):
        self.root_node();node=self.open()['node_id']
        old=self.director(node);self.director(node,scene_need='NEW_SUGGESTION')
        reply=self.call('author.save',node_id=node,source_packet_event_id=old['packet_event_id'],content={'literary_text':'VALID_OLD_PACKET_PROSE'})
        self.assertFalse(reply['source_is_latest'])
        self.assertEqual(self.call('author.read',node_id=node)['reply']['director_packet_event_id'],old['packet_event_id'])

    def test_low_level_create_revise_and_action_filter_use_same_contract(self):
        self.root_node();self.scene(node='low-level',publish=False)
        first=self.event(node='low-level',event_id='low-first')['event']
        replacement=self.call('event.create',node_id='low-level',
            object={'object_id':'memory-player','object_type':'role_memory','object_key':'memory-player','name':'记忆'},
            event={'event_id':'low-replacement','event_type':'role_memory','type_name':'player','event_action':'replace',
                   'content':{'claim':'REPLACED_LOW_LEVEL'}},target_event_ids=[first['event_id']])['event']
        self.call('node.publish',node_id='low-level')
        self.call('node.revise',node_id='low-level',
            object={'object_id':'memory-player','object_type':'role_memory','object_key':'memory-player','name':'记忆'},
            event={'event_id':'low-cancel','event_type':'role_memory','type_name':'player','event_action':'cancel'},
            target_event_ids=[replacement['event_id']])
        filtered=self.call('object.events',object_id='memory-player',event_action='cancel',fields=['event_id','event_action'])
        self.assertEqual(filtered['items'],[{'event_id':'low-cancel','event_action':'cancel'}])
        self.assertEqual(self.claims('low-level'),[])
        self.assertEqual(len(self.call('business.read',node_id='low-level',kind='role_memory',include_history=True)['history']),3)

    def test_batch_targets_earlier_record_and_cancel_does_not_restore_replaced_content(self):
        self.root_node();node=self.open()['node_id']
        a=self.save(node,'ORIGINAL')
        commands=[{'operation':'business.save','params':{'node_id':node,'kind':'role_memory','key':'player',
            'event_id':'batch-replacement','event_action':'replace','target_event_ids':[a['event_id']],
            'content':{'character_id':'player','claim':'REPLACEMENT'}}},
            {'operation':'business.save','params':{'node_id':node,'kind':'role_memory','key':'player',
            'event_action':'cancel','target_event_ids':['batch-replacement']}}]
        self.call('batch',commands=commands)
        self.assertEqual(self.claims(node),[])
        self.save(node,'RESTORED_AS_NEW')
        self.assertEqual(self.claims(node),['RESTORED_AS_NEW'])

    def test_disabled_capsule_api_has_no_write(self):
        settings=deepcopy(self.app.resources.settings)
        settings['creative']['capsule_mode']=False
        self.app.resources=replace(self.app.resources,settings=settings)
        self.root_node();node=self.open()['node_id']
        source=self.save(node,'SOURCE')
        before=self.call('database.info')['counts']
        result=execute(self.app,{'operation':'capsule.save','params':{'node_id':node,'content':{'capsules':[{
            'object_id':'role_memory_player','level':1,'source_event_ids':[source['event_id']],
            'content':{'summary':'TEST_SUMMARY'}}]}}})
        self.assertFalse(result['ok'],result)
        self.assertEqual(result['error']['code'],'CAPSULE_DISABLED')
        self.assertEqual(self.call('database.info')['counts'],before)
