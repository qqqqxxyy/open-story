from common import FunctionalCase
import json


class Sample(FunctionalCase):
    def test_item_import_preserves_raw_input_prose_and_business_content(self):
        src=self.root/'v5-source';(src/'nodes/root-unused').mkdir(parents=True)
        (src/'nodes/node-root').mkdir();(src/'nodes/first').mkdir()
        def write(relative,value):
            (src/relative).write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
        write('story.json',{'version':4,'id':'fixture-story','title':'铃声样本','tone':['生活感']})
        write('nodes/node-root/meta.json',{'kind':'root','node_id':'node-root','creation_parent_id':None,'display_index':0})
        write('nodes/node-root/snapshot.json',{'version':4,'story_id':'fixture-story','node_id':'node-root',
            'characters':{},'author_notes':'中文风格说明','director':{'story_phase':'opening'}})
        write('nodes/first/meta.json',{'kind':'scene','node_id':'first','creation_parent_id':'node-root','display_index':1})
        original={'raw_user_messages':[{'text':'原话\n保留错字。','source':'assistant_transcribed'}],'interpreted_intent':'另存解释'}
        write('nodes/first/input.json',original)
        prose='铃响了。\n\n他看向门口。\n';(src/'nodes/first/narrative.md').write_text(prose,encoding='utf8',newline='')
        write('nodes/first/delta.json',{'scene':{'summary':'听见铃声','time':'早晨','location':'教室'},
            'character_upserts':[{'id':'player','name':'示例主角','traits':{'不固定的栏目':['好奇']}}],
            'memories_add':[{'character_id':'player','id':'m1','claim':'听到了铃声','source':{'node_id':'first'}},
                            {'character_id':'player','id':'m2','claim':'看向门口'}],
            'facts_add':[{'id':'f1','claim':'门关着'}]})
        imported=self.call('sample.import_v5',source_story=str(src))
        self.assertEqual(imported['counts']['node'],2)
        self.assertEqual(self.call('node.read',node_id='first')['narrative'],prose)
        self.assertEqual(self.call('node.read',node_id='first')['summary'],'听见铃声')
        memory=self.call('object.events',object_id='role_memory_player')
        self.assertEqual(memory['total'],2)
        self.assertEqual([e['content']['claim'] for e in memory['items']],['听到了铃声','看向门口'])
        inputs=self.call('node.events',node_id='first',event_type='user_input')
        self.assertEqual(inputs['items'][0]['content'],original)
        self.assertEqual(len(imported['mappings']),imported['counts']['event'])
        twice=self.call('sample.import_v5',source_story=str(src))
        self.assertEqual(twice['counts'],imported['counts'])
