"""Reader feedback, manuscript identity and default narrative visibility."""
from creative_common import CreativeCase
from unittest.mock import patch
from script.cli.main import execute


class SceneRevision(CreativeCase):
    def prepare(self,request='one',**options):
        return self.call('scene.prepare',branch_id='main',action='next',request_id=request,
            content={'raw_user_messages':[{'text':request,'source':'simulation'}]},**options)

    def submit(self,opened,text='FIRST'):
        node=opened['scene']['node_id'];aid=opened['attempt']['attempt_id']
        source=self.director(node)['packet_event_id']
        return self.call('scene.submit',node_id=node,attempt_id=aid,source_packet_event_id=source,
            content={'literary_text':text,'display':{'summary':text,'location':'TEST','time':'DAY','participants':['player']}},
            output_root=str(self.root/'reader'),generate=False)

    def test_minor_revision_has_no_recall_and_keeps_old_manuscript(self):
        self.root_node();opened=self.prepare();first=self.submit(opened)
        self.assertEqual(first['status'],'awaiting_feedback')
        self.assertIsNone(first['maintenance']['next_job'])
        params={'node_id':opened['scene']['node_id'],'branch_id':'main','action':'revise',
            'revision_kind':'minor','request_id':'fix','base_author_packet_event_id':first['author_packet_event_id'],
            'content':{'raw_user_messages':[{'text':'只改最后一句','source':'simulation'}]}}
        with patch('script.workflow.pipeline.creative.recall.recall',side_effect=AssertionError('unexpected recall')):
            revision=self.call('scene.prepare',**params)
        self.assertIsNone(revision['preparation'])
        self.assertEqual(revision['scene']['node_id'],opened['scene']['node_id'])
        old=self.call('author.read',node_id=opened['scene']['node_id'],packet_event_id=first['author_packet_event_id'])
        self.assertEqual(old['literary_text'],'FIRST')
        source=self.call('record.get',entity='event',record_id=first['author_packet_event_id'])['content']['director_packet_event_id']
        second=self.call('scene.submit',node_id=opened['scene']['node_id'],attempt_id=revision['attempt']['attempt_id'],
            source_packet_event_id=source,content={'literary_text':'SECOND','display':{'summary':'SECOND','location':'TEST','time':'DAY','participants':['player']}},
            output_root=str(self.root/'reader'),generate=False)
        self.assertNotEqual(first['narrative_event_id'],second['narrative_event_id'])
        self.assertEqual(second['status'],'awaiting_feedback')
        self.assertEqual(self.call('history.list',branch_id='main')['total'],0)

    def test_next_adopts_previous_without_semantic_archive_and_retries(self):
        self.root_node();one=self.prepare();reply=self.submit(one)
        two=self.prepare('two',expected_author_packet_event_id=reply['author_packet_event_id'],output_root=str(self.root/'reader'))
        self.assertEqual(two['preparation']['previous_scene_prose'],'FIRST')
        self.assertEqual(self.prepare('two')['scene']['node_id'],two['scene']['node_id'])
        oneid=one['scene']['node_id']
        self.assertEqual(self.call('scene.status',node_id=oneid)['status'],'accepted_pending_archive')
        events=self.call('record.list',entity='event',filters={'event_type':'director_archive'})
        self.assertEqual(events['total'],0)
        self.assertEqual(self.call('history.list',branch_id='main')['total'],1)

    def test_major_revision_uses_new_feedback_and_current_attempt(self):
        self.root_node();one=self.prepare();reply=self.submit(one)
        change=self.call('scene.prepare',node_id=one['scene']['node_id'],branch_id='main',action='revise',
            revision_kind='major',request_id='major',base_author_packet_event_id=reply['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'改为合作寻物','source':'simulation'}]})
        self.assertIsNotNone(change['preparation'])
        ctx=change['preparation']['scope']
        raw=self.call('context.read',node_id=one['scene']['node_id'],event_ids=ctx['raw_input_event_ids'])
        self.assertTrue(any('合作寻物' in str(row['event']['content']) for row in raw['sources']))
        bad=execute(self.app,{'operation':'scene.submit','params':{'node_id':one['scene']['node_id'],
            'attempt_id':one['attempt']['attempt_id'],'source_packet_event_id':reply.get('source_packet_event_id','bad'),
            'content':{'literary_text':'STALE','display':{'summary':'STALE','location':'TEST','time':'DAY','participants':['player']}},'generate':False}})
        self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],'STALE_MANUSCRIPT')

    def test_draft_cannot_enter_normal_prose_lookup(self):
        self.root_node();one=self.prepare();self.submit(one)
        result=execute(self.app,{'operation':'context.read','params':{'node_id':one['scene']['node_id'],
            'view':'prose','source_node_ids':[one['scene']['node_id']]}})
        self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'DRAFT_NOT_ADOPTED')


    def test_reviewed_dialogue_keeps_original_turns_and_allows_complete_minor_revision(self):
        self.root_node();opened=self.prepare(mode='dialogue');node=opened['scene']['node_id']
        source=self.director(node)['packet_event_id'];first=opened['scene']['raw_input_event_ids'][0]
        saved=self.call('dialogue.save',node_id=node,turn_id=first,
            content={'literary_text':'ORIGINAL_FRAGMENT','scene_complete':False})
        turn=self.call('dialogue.input',node_id=node,
            content={'raw_user_messages':[{'text':'接着说','source':'simulation'}]})['turn_id']
        completed=self.call('dialogue.save',node_id=node,turn_id=turn,
            content={'literary_text':'LAST_FRAGMENT','scene_complete':True,'final_literary_text':'REVIEWED_COMPLETE'})
        metadata={'summary':'DONE','location':'ROOM','time':'DAY','participants':[]}
        shown=self.call('scene.submit',node_id=node,attempt_id=opened['attempt']['attempt_id'],
            author_packet_event_id=completed['packet_event_id'],content={'display':metadata},
            output_root=str(self.root/'reader'),generate=False)
        self.assertEqual(self.call('author.read',node_id=node,packet_event_id=completed['packet_event_id'])['literary_text'],'REVIEWED_COMPLETE')
        fragment=self.call('dialogue.read',node_id=node,fragment_event_id=saved['fragment_event_id'])
        self.assertEqual(fragment['fragments'][0]['content']['literary_text'],'ORIGINAL_FRAGMENT')
        revision=self.call('scene.prepare',node_id=node,action='revise',revision_kind='minor',request_id='dialogue-fix',
            base_author_packet_event_id=shown['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'只改收束','source':'simulation'}]})
        revised=self.call('scene.submit',node_id=node,attempt_id=revision['attempt']['attempt_id'],
            source_packet_event_id=source,content={'literary_text':'REVISED_DIALOGUE','display':metadata},
            output_root=str(self.root/'reader'),generate=False)
        self.assertEqual(revised['status'],'awaiting_feedback')
        self.assertNotEqual(revised['narrative_event_id'],shown['narrative_event_id'])

    def test_major_cannot_reuse_base_director_and_drafts_cannot_be_pinned(self):
        self.root_node();opened=self.prepare();one=self.submit(opened);node=opened['scene']['node_id']
        source=self.call('record.get',entity='event',record_id=one['author_packet_event_id'])['content']['director_packet_event_id']
        revision=self.call('scene.prepare',node_id=node,action='revise',revision_kind='major',request_id='new-design',
            base_author_packet_event_id=one['author_packet_event_id'],
            content={'raw_user_messages':[{'text':'换一个主要矛盾','source':'simulation'}]})
        bad=execute(self.app,{'operation':'author.save','params':{'node_id':node,
            'attempt_id':revision['attempt']['attempt_id'],'source_packet_event_id':source,'content':{'literary_text':'BAD'}}})
        self.assertFalse(bad['ok']);self.assertEqual(bad['error']['code'],'PACKET_REFERENCE_REQUIRED')
        for operation,params in [('scene.context',{'event_ids':[one['narrative_event_id']],'view':'full'}),('author.read',{})]:
            result=execute(self.app,{'operation':operation,'params':{'node_id':node,**params}})
            self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'DRAFT_NOT_ADOPTED')
        result=self.submit(revision,'NEW_DESIGN')
        self.assertEqual(result['status'],'awaiting_feedback')
        self.assertEqual(self.call('scene.status',node_id=node)['status'],'awaiting_feedback')

    def test_failed_display_keeps_manuscript_and_reuses_current_attempt(self):
        from script.util.errors import ContractError
        self.root_node();opened=self.prepare();node=opened['scene']['node_id'];source=self.director(node)['packet_event_id']
        metadata={'summary':'READY','location':'ROOM','time':'DAY','participants':[]}
        params={'node_id':node,'attempt_id':opened['attempt']['attempt_id'],'source_packet_event_id':source,
            'content':{'literary_text':'SAVED_BEFORE_DISPLAY','display':metadata},'output_root':str(self.root/'reader'),'generate':False}
        with patch('script.workflow.pipeline.creative.presentation.sync',side_effect=ContractError('DISPLAY_FAILED','test failure')):
            failed=execute(self.app,{'operation':'scene.submit','params':params})
        self.assertFalse(failed['ok']);details=failed['error']['details']
        restored=self.call('scene.prepare',node_id=node,action='resume')
        self.assertEqual(restored['next_action'],'restore_display')
        self.assertIsNone(restored['preparation'])
        blocked=execute(self.app,{'operation':'scene.prepare','params':{'branch_id':'main','action':'next','request_id':'premature',
            'expected_author_packet_event_id':details['author_packet_event_id'],
            'content':{'raw_user_messages':[{'text':'NEXT','source':'simulation'}]}}})
        self.assertFalse(blocked['ok']);self.assertEqual(blocked['error']['code'],'DISPLAY_REQUIRED')
        retry={'node_id':node,'attempt_id':opened['attempt']['attempt_id'],
            'author_packet_event_id':details['author_packet_event_id'],'content':{'display':metadata},
            'output_root':str(self.root/'reader'),'generate':False}
        good=self.call('scene.submit',**retry);again=self.call('scene.submit',**retry)
        self.assertEqual(good['status'],'awaiting_feedback');self.assertEqual(good['narrative_event_id'],details['narrative_event_id'])
        self.assertFalse(again['display']['snapshot_changed'])
        self.assertEqual(again['display']['changed_node_ids'],[])

    def test_real_cli_uses_new_prepare_and_complete_file_output(self):
        import subprocess,sys,json
        from common import REPO
        self.root_node();payload=self.root/'input.json';output=self.root/'prepared.json'
        payload.write_text(json.dumps({'raw_user_messages':[{'text':'中文原话“继续”','source':'simulation'}]},ensure_ascii=False),encoding='utf8')
        result=subprocess.run([sys.executable,'-B','-X','utf8',str(REPO/'script/cli/main.py'),'scene-prepare',
            '--config',str(self.config),'--action','next','--request-id','real-cli','--content-file',str(payload),'--output-file',str(output)],
            capture_output=True,text=True,encoding='utf8',check=True)
        receipt=json.loads(result.stdout);value=json.loads(output.read_text(encoding='utf8'))
        self.assertTrue(value['ok'],value);self.assertEqual(receipt['data']['output_file'],str(output.resolve()))
        self.assertIsNotNone(value['data']['attempt']['attempt_id']);self.assertEqual(value['data']['next_action'],'design_scene')
        self.assertNotIn('中文原话',str(value['data']['attempt']))


    def test_request_identity_cannot_change_mode_or_input(self):
        self.root_node();one=self.prepare()
        for patch_params in ({'mode':'dialogue'},{'content':{'raw_user_messages':[{'text':'DIFFERENT','source':'simulation'}]}}):
            params={'branch_id':'main','action':'next','request_id':'one','content':{'raw_user_messages':[{'text':'one','source':'simulation'}]},**patch_params}
            result=execute(self.app,{'operation':'scene.prepare','params':params})
            self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'IDEMPOTENCY_CONFLICT')
        self.assertEqual(self.prepare()['scene']['node_id'],one['scene']['node_id'])


    def test_new_workflow_opens_existing_blank_fork_draft(self):
        self.root_node();self.ordinary();self.call('branch.fork',branch_id='side',from_node_id='root',node_id='side-draft')
        opened=self.call('scene.prepare',branch_id='side',action='next',request_id='side-one',
            content={'raw_user_messages':[{'text':'NEW_BRANCH','source':'simulation'}]})
        self.assertEqual(opened['scene']['node_id'],'side-draft')
        self.assertIsNotNone(opened['attempt'])
        self.assertIsNone(opened['accepted_predecessor'])

    def test_same_body_metadata_revision_requires_new_display(self):
        from script.util.errors import ContractError
        self.root_node();opened=self.prepare();one=self.submit(opened);node=opened['scene']['node_id']
        source=self.call('record.get',entity='event',record_id=one['author_packet_event_id'])['content']['director_packet_event_id']
        change=self.call('scene.prepare',node_id=node,action='revise',request_id='metadata-fix',revision_kind='minor',
            base_author_packet_event_id=one['author_packet_event_id'],content={'raw_user_messages':[{'text':'仅修改展示摘要','source':'simulation'}]})
        with patch('script.workflow.pipeline.creative.presentation.sync',side_effect=ContractError('DISPLAY_FAILED','test')):
            failed=execute(self.app,{'operation':'scene.submit','params':{'node_id':node,'attempt_id':change['attempt']['attempt_id'],
                'source_packet_event_id':source,'content':{'literary_text':'FIRST','display':{'summary':'NEW_SUMMARY','location':'TEST','time':'DAY','participants':['player']}},
                'output_root':str(self.root/'reader'),'generate':False}})
        self.assertFalse(failed['ok'])
        status=self.call('scene.status',node_id=node)
        self.assertFalse(status['display_snapshot_available'])
        self.assertEqual(status['status'],'awaiting_display')
        adoption=execute(self.app,{'operation':'scene.accept','params':{'node_id':node,'branch_id':'main','request_id':'premature-adopt',
            'author_packet_event_id':failed['error']['details']['author_packet_event_id']}})
        self.assertFalse(adoption['ok']);self.assertEqual(adoption['error']['code'],'DISPLAY_REQUIRED')

    def test_unshown_manuscript_cannot_start_reader_revision(self):
        from script.util.errors import ContractError
        self.root_node();opened=self.prepare();node=opened['scene']['node_id']
        with patch('script.workflow.pipeline.creative.presentation.sync',side_effect=ContractError('DISPLAY_FAILED','test')):
            try:self.submit(opened)
            except AssertionError:pass
        packet=self.call('scene.status',node_id=node)['author_reply_event_id']
        revision=execute(self.app,{'operation':'scene.prepare','params':{'node_id':node,'action':'revise','revision_kind':'minor',
            'request_id':'not-seen','base_author_packet_event_id':packet,
            'content':{'raw_user_messages':[{'text':'REVISION','source':'simulation'}]}}})
        self.assertFalse(revision['ok']);self.assertEqual(revision['error']['code'],'DISPLAY_REQUIRED')

    def test_displayed_legacy_draft_can_enter_minor_revision(self):
        self.root_node();old=self.open();node=old['node_id'];source=self.director(node)['packet_event_id']
        author=self.call('author.save',node_id=node,source_packet_event_id=source,content={'literary_text':'LEGACY'})
        self.call('scene.display',node_id=node,content={'summary':'OLD','location':'ROOM','time':'DAY','participants':[]},
            output_root=str(self.root/'reader'),generate=False)
        changed=self.call('scene.prepare',node_id=node,action='revise',request_id='legacy-fix',revision_kind='minor',output_root=str(self.root/'reader'),
            base_author_packet_event_id=author['packet_event_id'],content={'raw_user_messages':[{'text':'LOCAL_FIX','source':'simulation'}]})
        self.assertIsNone(changed['preparation']);self.assertEqual(changed['attempt']['kind'],'minor')

    def test_close_retry_does_not_silently_ignore_changed_review_text(self):
        self.root_node();opened=self.prepare(mode='dialogue');node=opened['scene']['node_id'];self.director(node)
        self.call('dialogue.save',node_id=node,turn_id=opened['scene']['raw_input_event_ids'][0],
            content={'literary_text':'TURN','scene_complete':False})
        saved=self.call('dialogue.close',node_id=node,content={'final_literary_text':'FINAL'})
        same=self.call('dialogue.close',node_id=node,content={'final_literary_text':'FINAL'})
        self.assertEqual(saved['packet_event_id'],same['packet_event_id'])
        changed=execute(self.app,{'operation':'dialogue.close','params':{'node_id':node,'content':{'final_literary_text':'DIFFERENT'}}})
        self.assertFalse(changed['ok']);self.assertEqual(changed['error']['code'],'IDEMPOTENCY_CONFLICT')


    def test_resume_after_display_before_maintenance_returns_pending_job(self):
        from script.util.errors import ContractError
        self.root_node();first=self.prepare();one=self.submit(first)
        second=self.prepare('two',expected_author_packet_event_id=one['author_packet_event_id'])
        node=second['scene']['node_id'];source=self.director(node)['packet_event_id']
        with patch('script.workflow.pipeline.creative.maintenance.inspect',side_effect=ContractError('OPERATION_FAILED','after display')):
            failed=execute(self.app,{'operation':'scene.submit','params':{'node_id':node,'attempt_id':second['attempt']['attempt_id'],
                'source_packet_event_id':source,'content':{'literary_text':'SECOND','display':{'summary':'SECOND','location':'TEST','time':'DAY','participants':[]}},
                'output_root':str(self.root/'reader'),'generate':False}})
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['error'].get('details',{}).get('completed_stage'),'display_published')
        resumed=self.call('scene.prepare',node_id=node,action='resume')
        self.assertEqual(resumed['next_operation'],'scene.maintenance')
        self.assertEqual(resumed['maintenance']['next_job']['node_id'],first['scene']['node_id'])
        self.assertIsNone(resumed['preparation'])

    def test_saved_dialogue_fragment_does_not_duplicate_the_final_review_body(self):
        self.root_node();opened=self.prepare(mode='dialogue');node=opened['scene']['node_id'];self.director(node)
        result=self.call('dialogue.save',node_id=node,turn_id=opened['scene']['raw_input_event_ids'][0],
            content={'literary_text':'FRAGMENT','scene_complete':True,'final_literary_text':'REVIEWED_COMPLETE_BODY'})
        fragment=self.call('record.get',entity='event',record_id=result['fragment_event_id'])
        self.assertNotIn('final_literary_text',fragment['content'])
        self.assertEqual(self.call('author.read',node_id=node,packet_event_id=result['packet_event_id'])['literary_text'],'REVIEWED_COMPLETE_BODY')


    def test_resume_prepared_author_or_open_dialogue_does_not_recall_again(self):
        self.root_node();opened=self.prepare();node=opened['scene']['node_id'];self.director(node)
        with patch('script.workflow.pipeline.creative.recall.recall',side_effect=AssertionError('unexpected recall')):
            resumed=self.call('scene.prepare',node_id=node,action='resume')
        self.assertEqual(resumed['next_action'],'write_prose');self.assertIsNone(resumed['preparation'])
        one=self.submit(opened)
        dialogue=self.prepare('dialogue-next',mode='dialogue',expected_author_packet_event_id=one['author_packet_event_id'])
        node=dialogue['scene']['node_id'];self.director(node)
        with patch('script.workflow.pipeline.creative.recall.recall',side_effect=AssertionError('unexpected recall')):
            resumed=self.call('scene.prepare',node_id=node,action='resume')
        self.assertEqual(resumed['next_operation'],'dialogue.read');self.assertIsNone(resumed['preparation'])

    def test_legacy_unfinished_recovery_can_attach_an_attempt_without_new_node(self):
        self.root_node();old=self.open();node=old['node_id']
        restored=self.call('scene.prepare',node_id=node,action='resume',request_id='adopt-legacy-task')
        self.assertEqual(restored['scene']['node_id'],node);self.assertIsNotNone(restored['attempt'])
        self.assertEqual(self.call('scene.prepare',node_id=node,action='resume')['attempt']['attempt_id'],restored['attempt']['attempt_id'])
        shown=self.submit(restored,'RECOVERED')
        self.assertEqual(shown['status'],'awaiting_feedback')

    def test_old_draft_prose_and_metadata_stay_out_of_queries_after_new_version_is_adopted(self):
        self.root_node();opened=self.prepare();first=self.submit(opened,'DISCARDED_WORDS');node=opened['scene']['node_id']
        source=self.call('record.get',entity='event',record_id=first['author_packet_event_id'])['content']['director_packet_event_id']
        changed=self.call('scene.prepare',node_id=node,action='revise',request_id='replace-body',revision_kind='minor',
            base_author_packet_event_id=first['author_packet_event_id'],content={'raw_user_messages':[{'text':'换掉原文','source':'simulation'}]})
        latest=self.call('scene.submit',node_id=node,attempt_id=changed['attempt']['attempt_id'],source_packet_event_id=source,
            content={'literary_text':'ADOPTED_WORDS','display':{'summary':'ADOPTED_SUMMARY','location':'ROOM','time':'DAY','participants':[]}},
            output_root=str(self.root/'reader'),generate=False)
        next_scene=self.prepare('following',expected_author_packet_event_id=latest['author_packet_event_id'])
        result=self.call('context.read',node_id=next_scene['scene']['node_id'],event_types=['narrative','author_packet','display_metadata','scene_summary'])
        ids={row['event']['event_id'] for row in result['sources']}
        self.assertNotIn(first['narrative_event_id'],ids);self.assertNotIn(first['author_packet_event_id'],ids);self.assertNotIn(first['display_event_id'],ids)
        search=self.call('history.search',branch_id='main',keyword='DISCARDED_WORDS')
        self.assertEqual(search['total'],0)


    def test_nonrevision_discussion_does_not_invalidate_displayed_manuscript(self):
        self.root_node();opened=self.prepare();one=self.submit(opened);node=opened['scene']['node_id']
        self.call('business.save',node_id=node,kind='user_input',key='discussion',
            content={'raw_user_messages':[{'text':'只讨论后续，不改当前稿','source':'simulation'}]})
        self.director(node,interpreted_intent='LATER_DISCUSSION_NOT_USED_BY_AUTHOR')
        self.assertEqual(self.call('scene.status',node_id=node)['status'],'awaiting_feedback')
        next_scene=self.prepare('after-discussion',expected_author_packet_event_id=one['author_packet_event_id'])
        self.assertEqual(next_scene['preparation']['previous_scene_prose'],'FIRST')

    def test_display_recovery_inherits_saved_reader_location_and_generation_choice(self):
        from script.util.errors import ContractError
        self.root_node();opened=self.prepare();node=opened['scene']['node_id'];source=self.director(node)['packet_event_id']
        metadata={'summary':'READY','location':'ROOM','time':'DAY','participants':[]}
        with patch('script.workflow.pipeline.creative.presentation.sync',side_effect=ContractError('DISPLAY_FAILED','test')):
            failed=execute(self.app,{'operation':'scene.submit','params':{'node_id':node,'attempt_id':opened['attempt']['attempt_id'],
                'source_packet_event_id':source,'content':{'literary_text':'SAVED','display':metadata},
                'output_root':str(self.root/'custom-reader'),'generate':False}})
        reply=failed['error']['details']['author_packet_event_id']
        recovered=self.call('scene.submit',node_id=node,attempt_id=opened['attempt']['attempt_id'],author_packet_event_id=reply,
            content={'display':metadata})
        self.assertEqual(recovered['status'],'awaiting_feedback')
        self.assertTrue(str(recovered['display']['snapshot_path']).startswith(str(self.root/'custom-reader')))


    def test_old_html_cannot_validate_new_metadata_with_the_same_body(self):
        from script.workflow.pipeline.creative import presentation
        from script.util.errors import ContractError
        self.root_node();opened=self.prepare();one=self.submit(opened);node=opened['scene']['node_id']
        self.call('display.export',output_root=str(self.root/'reader'),generate=True)
        source=self.call('record.get',entity='event',record_id=one['author_packet_event_id'])['content']['director_packet_event_id']
        revision=self.call('scene.prepare',node_id=node,action='revise',request_id='html-fix',revision_kind='minor',
            base_author_packet_event_id=one['author_packet_event_id'],content={'raw_user_messages':[{'text':'改摘要','source':'simulation'}]})
        original=presentation.sync
        def snapshot_then_fail(repository,params):
            original(repository,{**params,'generate':False})
            raise ContractError('DISPLAY_FAILED','HTML generation interrupted')
        with patch('script.workflow.pipeline.creative.presentation.sync',side_effect=snapshot_then_fail):
            failed=execute(self.app,{'operation':'scene.submit','params':{'node_id':node,'attempt_id':revision['attempt']['attempt_id'],
                'source_packet_event_id':source,'content':{'literary_text':'FIRST','display':{'summary':'NEW_METADATA','location':'TEST','time':'DAY','participants':[]}},
                'output_root':str(self.root/'reader'),'generate':True}})
        self.assertFalse(failed['ok']);state=self.call('scene.status',node_id=node)
        self.assertTrue(state['display_snapshot_available']);self.assertFalse(state['display_html_available'])
        self.assertEqual(state['status'],'awaiting_display')

    def test_accept_interruption_and_pending_ancestor_resume_keep_the_actual_stage(self):
        from script.util.errors import ContractError
        self.root_node();opened=self.prepare();one=self.submit(opened);node=opened['scene']['node_id']
        with patch('script.workflow.pipeline.creative.maintenance.inspect',side_effect=ContractError('OPERATION_FAILED','after adoption')):
            failed=execute(self.app,{'operation':'scene.accept','params':{'node_id':node,'branch_id':'main',
                'author_packet_event_id':one['author_packet_event_id'],'request_id':'finish'}})
        self.assertFalse(failed['ok']);self.assertEqual(failed['error']['details']['completed_stage'],'manuscript_accepted')
        restored=self.call('scene.prepare',node_id=node,action='resume')
        self.assertEqual(restored['maintenance']['next_job']['node_id'],node)
        second=self.prepare('second')
        old=self.call('scene.prepare',node_id=node,action='resume')
        self.assertEqual(old['next_action'],'resume_branch_head')
        self.assertEqual(old['resume_node_id'],second['scene']['node_id'])
