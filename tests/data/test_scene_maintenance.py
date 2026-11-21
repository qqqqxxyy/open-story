"""Post-display maintenance uses adopted ancestors and its own frozen scope."""
from creative_common import CreativeCase
from copy import deepcopy
from dataclasses import replace
from script.cli.main import execute


class SceneMaintenance(CreativeCase):
    def pair(self):
        self.root_node()
        first=self.call('scene.prepare',branch_id='main',action='next',request_id='first',
            content={'raw_user_messages':[{'text':'FIRST','source':'simulation'}]})
        one=self.show(first,'FIRST')
        second=self.call('scene.prepare',branch_id='main',action='next',request_id='second',
            expected_author_packet_event_id=one['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'SECOND','source':'simulation'}]})
        two=self.show(second,'SECOND')
        return first,one,second,two

    def show(self,opened,text):
        node=opened['scene']['node_id'];source=self.director(node)['packet_event_id']
        return self.call('scene.submit',node_id=node,attempt_id=opened['attempt']['attempt_id'],
            source_packet_event_id=source,content={'literary_text':text,
                'display':{'summary':text,'location':'TEST','time':'DAY','participants':['player']}},
            output_root=str(self.root/'reader'),generate=False)

    def apply(self,reply,job,**content):
        return self.call('scene.maintenance',branch_id='main',trigger_author_packet_event_id=reply['author_packet_event_id'],
                         job_id=job['job_id'],content=content)

    def test_display_precedes_nonleaf_archive_and_fixed_scene_scope_stays_fixed(self):
        first,one,second,two=self.pair()
        job=two['maintenance']['next_job']
        self.assertEqual(job['node_id'],first['scene']['node_id'])
        self.assertEqual(job['phase'],'semantic_pending')
        snapshots={str(p.relative_to(self.root/'reader')):p.read_bytes() for p in (self.root/'reader').rglob('*') if p.is_file()}
        entries=[{'kind':'world_fact','key':'late','content':{'id':'late','text':'LATE_ARCHIVE'}}]
        done=self.apply(two,job,events=entries)
        self.assertTrue(done['complete']);self.assertIsNone(done['next_job'])
        self.assertEqual(snapshots,{str(p.relative_to(self.root/'reader')):p.read_bytes() for p in (self.root/'reader').rglob('*') if p.is_file()})
        self.assertEqual(self.call('branch.read',branch_id='main')['head']['node_id'],second['scene']['node_id'])
        same=self.call('scene.context',node_id=second['scene']['node_id'])
        self.assertEqual(same['projection']['world_fact'],[])
        self.assertEqual(same['previous_scene_prose'],'FIRST')
        third=self.call('scene.prepare',branch_id='main',action='next',request_id='third',
            expected_author_packet_event_id=two['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'THIRD','source':'simulation'}]})
        self.assertEqual(third['preparation']['projection']['world_fact'][0]['event']['content']['text'],'LATE_ARCHIVE')
        self.assertEqual(self.call('scene.status',node_id=first['scene']['node_id'])['status'],'complete')

    def test_future_sources_rejected_and_semantic_retry_is_idempotent(self):
        first,one,second,two=self.pair();job=two['maintenance']['next_job']
        entries=[{'kind':'role_memory','key':'player','content':{'character_id':'player','claim':'MEMORY'},
                  'source_event_ids':[two['narrative_event_id']]}]
        bad=execute(self.app,{'operation':'scene.maintenance','params':{'branch_id':'main',
            'trigger_author_packet_event_id':two['author_packet_event_id'],'job_id':job['job_id'],'content':{'events':entries}}})
        self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],'SOURCE_NOT_VISIBLE')
        self.assertEqual(self.call('record.list',entity='event',filters={'event_type':'director_archive'})['total'],0)
        entries[0].pop('source_event_ids')
        self.apply(two,job,events=entries)
        before=self.call('record.list',entity='event')['total']
        self.apply(two,job,events=entries)
        self.assertEqual(self.call('record.list',entity='event')['total'],before)

    def test_capsule_batches_and_second_level_are_advanced_by_api(self):
        settings=deepcopy(self.app.resources.settings)
        settings['creative']['capsule_mode']=True
        settings['creative']['capsule']['defaults'].update(level_1_events=2,level_2_capsules=2)
        self.app.resources=replace(self.app.resources,settings=settings)
        first,one,second,two=self.pair();job=two['maintenance']['next_job']
        result=self.apply(two,job,events=[{'kind':'role_memory','key':'player',
            'content':{'character_id':'player','claim':'MEMORY_'+str(i)}} for i in range(4)])
        levels=[]
        while result['next_job']:
            current=result['next_job'];self.assertEqual(current['phase'],'capsule_pending')
            entries=[]
            for obj in current['capsule_jobs']['objects']:
                for level in (1,2):
                    for batch in obj['level_'+str(level)]['batches']:
                        levels.append(level)
                        entries.append({'object_id':obj['object_id'],'level':level,
                            'source_event_ids':batch['source_event_ids'],'supersedes_capsule_event_ids':batch['supersedes_capsule_event_ids'],
                            'content':{'summary':'CAPSULE '+str(level)}})
            self.assertTrue(entries)
            result=self.apply(two,current,capsules=entries)
            replay=self.apply(two,current,capsules=entries)
            self.assertEqual(replay,result)
        self.assertEqual(levels,[1,1,2])
        self.assertEqual(self.call('scene.status',node_id=first['scene']['node_id'])['status'],'complete')
        self.assertEqual(self.call('scene.status',node_id=second['scene']['node_id'],output_root=str(self.root/'reader'))['status'],'awaiting_feedback')

    def test_explicit_accept_finishes_tail_but_does_not_archive_automatically(self):
        self.root_node()
        opened=self.call('scene.prepare',branch_id='main',action='next',request_id='only',
            content={'raw_user_messages':[{'text':'ONLY','source':'simulation'}]})
        reply=self.show(opened,'ONLY')
        accepted=self.call('scene.accept',node_id=opened['scene']['node_id'],branch_id='main',
            author_packet_event_id=reply['author_packet_event_id'],request_id='finish')
        self.assertEqual(accepted['status'],'accepted_pending_archive')
        self.assertTrue(self.apply(reply,accepted['maintenance']['next_job'],events=[])['complete'])


    def test_maintenance_cannot_start_before_new_head_display(self):
        self.root_node()
        first=self.call('scene.prepare',action='next',request_id='first',
            content={'raw_user_messages':[{'text':'FIRST','source':'simulation'}]})
        one=self.show(first,'FIRST')
        second=self.call('scene.prepare',action='next',request_id='second',expected_author_packet_event_id=one['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'SECOND','source':'simulation'}]})
        blocked=execute(self.app,{'operation':'scene.maintenance','params':{'branch_id':'main','trigger_author_packet_event_id':one['author_packet_event_id']}})
        self.assertFalse(blocked['ok']);self.assertEqual(blocked['error']['code'],'MAINTENANCE_SCOPE')
        self.assertEqual(self.call('record.list',entity='event',filters={'event_type':'director_archive'})['total'],0)
        shown=self.show(second,'SECOND');job=shown['maintenance']['next_job']
        self.assertEqual(self.call('scene.maintenance',branch_id='main',trigger_author_packet_event_id=shown['author_packet_event_id'])['next_job']['job_id'],job['job_id'])

    def test_html_and_refresh_marker_stay_unchanged_during_semantic_maintenance(self):
        first,one,second,two=self.pair()
        self.call('display.export',output_root=str(self.root/'reader'),generate=True)
        files=[self.root/'reader/dist/index.html',self.root/'reader/dist/display-version.js']
        before=[p.read_bytes() for p in files]
        self.apply(two,two['maintenance']['next_job'],events=[])
        self.assertEqual(before,[p.read_bytes() for p in files])


    def test_shared_pending_ancestor_can_be_maintained_from_a_fork(self):
        self.root_node()
        first=self.call('scene.prepare',action='next',request_id='one',content={'raw_user_messages':[{'text':'ONE','source':'simulation'}]})
        one=self.show(first,'ONE')
        self.call('scene.prepare',action='next',request_id='two',expected_author_packet_event_id=one['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'TWO','source':'simulation'}]})
        self.call('branch.fork',branch_id='side',from_node_id=first['scene']['node_id'],node_id='side-draft')
        opened=self.call('scene.prepare',branch_id='side',action='next',request_id='side-one',
            content={'raw_user_messages':[{'text':'SIDE','source':'simulation'}]})
        source=self.director('side-draft')['packet_event_id']
        shown=self.call('scene.submit',branch_id='side',node_id='side-draft',attempt_id=opened['attempt']['attempt_id'],
            source_packet_event_id=source,content={'literary_text':'SIDE','display':{'summary':'SIDE','location':'ROOM','time':'DAY','participants':[]}},
            output_root=str(self.root/'reader'),generate=False)
        job=shown['maintenance']['next_job'];self.assertEqual(job['node_id'],first['scene']['node_id'])
        result=self.call('scene.maintenance',branch_id='side',trigger_author_packet_event_id=shown['author_packet_event_id'],
            job_id=job['job_id'],content={'events':[]})
        self.assertTrue(result['complete'])

    def test_maintenance_rejects_unrelated_late_local_source(self):
        first,one,second,two=self.pair();job=two['maintenance']['next_job'];node=first['scene']['node_id']
        late=self.call('business.save',node_id=node,kind='role_memory',key='player',
            content={'character_id':'player','claim':'LATER_INDEPENDENT_MAINTENANCE'})['event']['event_id']
        bad=execute(self.app,{'operation':'scene.maintenance','params':{'branch_id':'main','trigger_author_packet_event_id':two['author_packet_event_id'],
            'job_id':job['job_id'],'content':{'events':[{'kind':'role_memory','key':'player','content':{'character_id':'player','claim':'WRONG'},'source_event_ids':[late]}]}}})
        self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],'SOURCE_NOT_VISIBLE')


    def test_capsule_jobs_exclude_unrelated_late_local_records(self):
        settings=deepcopy(self.app.resources.settings);settings['creative']['capsule_mode']=True
        settings['creative']['capsule']['defaults'].update(level_1_events=2,level_2_capsules=2)
        self.app.resources=replace(self.app.resources,settings=settings)
        first,one,second,two=self.pair();job=two['maintenance']['next_job']
        late=self.call('business.save',node_id=first['scene']['node_id'],kind='role_memory',key='player',
            content={'character_id':'player','claim':'UNRELATED_LATE'})['event']['event_id']
        result=self.apply(two,job,events=[{'kind':'role_memory','key':'player','content':{'character_id':'player','claim':'VALID_'+str(i)}} for i in range(2)])
        current=result['next_job'];self.assertEqual(current['phase'],'capsule_pending')
        entries=[]
        for obj in current['capsule_jobs']['objects']:
            for batch in obj['level_1']['batches']:
                self.assertNotIn(late,batch['source_event_ids'])
                entries.append({'object_id':obj['object_id'],'level':1,'source_event_ids':batch['source_event_ids'],
                    'supersedes_capsule_event_ids':batch['supersedes_capsule_event_ids'],'content':{'summary':'VALID_ONLY'}})
        self.assertTrue(entries);self.assertTrue(self.apply(two,current,capsules=entries)['complete'])


    def test_recovery_query_can_use_the_frozen_job_scope_instead_of_opening_scope(self):
        first,one,second,two=self.pair();job=two['maintenance']['next_job']
        self.apply(two,job,events=[{'kind':'world_fact','key':'earlier','content':{'id':'earlier','text':'EARLIER_DELAYED_ARCHIVE'}}])
        third=self.call('scene.prepare',action='next',request_id='third',expected_author_packet_event_id=two['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'THIRD','source':'simulation'}]})
        shown=self.show(third,'THIRD');job=shown['maintenance']['next_job'];node=second['scene']['node_id']
        self.call('business.save',node_id=node,kind='world_fact',key='unrelated',content={'id':'unrelated','text':'UNRELATED_AFTER_JOB'})
        original=self.call('context.read',node_id=node,event_types=['world_fact'])
        self.assertNotIn('EARLIER_DELAYED_ARCHIVE',str(original['sources']))
        recovered=self.call('context.read',node_id=node,branch_id='main',maintenance_job_id=job['job_id'],event_types=['world_fact'])
        self.assertIn('EARLIER_DELAYED_ARCHIVE',str(recovered['sources']))
        self.assertNotIn('UNRELATED_AFTER_JOB',str(recovered['sources']))
        self.assertEqual(recovered['scope']['maintenance_job_id'],job['job_id'])
