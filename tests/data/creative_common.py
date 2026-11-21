from common import FunctionalCase


class CreativeCase(FunctionalCase):
    def open(self, mode='normal', raw='继续故事', node_id=None):
        params={'branch_id':'main','mode':mode,'content':{'raw_user_messages':[{'text':raw,'source':'simulation'}]}}
        if node_id:params['node_id']=node_id
        return self.call('scene_next',**params)

    def director(self,node_id,**content):
        return self.call('director.save',node_id=node_id,content={'interpreted_intent':'TEST_INTENT','scene_need':'TEST_SUGGESTION',**content})

    def finish(self,node_id,events=None,generate=False):
        self.call('scene.display',node_id=node_id,content={'summary':'TEST_SUMMARY','location':'TEST_LOCATION',
            'time':'TEST_TIME','participants':['player']},output_root=str(self.root/'reader'),generate=generate)
        return self.call('scene.archive',node_id=node_id,content={'events':events or []},
                         output_root=str(self.root/'reader'))

    def ordinary(self,raw='继续故事',events=None):
        scene=self.open(raw=raw);node=scene['node_id']
        self.director(node)
        self.call('author.save',node_id=node,content={'literary_text':'TEST_PROSE '+raw,'feedback':{}})
        self.finish(node,events)
        return node
