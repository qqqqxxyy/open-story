"""Legacy business meaning -> immutable event plan. No SQL and no target writes."""
from copy import deepcopy
from pathlib import Path
import json
from .inventory import Source, load, stable, digest
from .replay import apply_delta
from script.workflow.pipeline.creative.actions import package
from script.workflow.pipeline.creative.common import workflow_object, validate_content


class Planner:
    def __init__(self, source, branch_ids, default_branch):
        self.source=Source(source, branch_ids)
        if default_branch not in branch_ids:raise ValueError('Default branch must be retained')
        self.default_branch=default_branch
        self.events=[];self.by_id={};self.mappings=[];self.versions={};self.states={}
        self.deferred=[];self.excluded=[];self.backend=self.design_records()
        self.notebooks={}
        for f in (self.source.root/'.system/author-notebooks').glob('*.json'):
            v=load(f)
            for i,item in enumerate(v.get('entries', [])):
                refs=item.get('source_node_ids', [])
                if len(refs)==1 and refs[0] in self.source.nodes:
                    self.notebooks.setdefault(refs[0], []).append((f.relative_to(self.source.root).as_posix(),i,item))

    def add(self,node,kind,key,payload,file,pointer,action='append',targets=(),native=False, provenance_extra=None):
        source=self.source
        event_id=stable(source.story['id'],file,pointer)
        if event_id in self.by_id:
            if self.by_id[event_id]['node_id']!=node:raise ValueError('Conflicting source ownership')
            return event_id
        obj=workflow_object(kind,key)
        if kind in ('node_metadata','legacy_scene_annotation','legacy_creative_record','narrative_candidate','legacy_dialogue_record','legacy_stage_summary'):
            obj={'object_id':kind+'_workflow','object_type':kind,'object_key':'workflow','name':kind}
        if kind in ('world_fact','role_profile','role_memory','thread','historical_trace','relationship','author_notes','plan','truth','secret') and action!='cancel':
            validate_content(kind,payload)
        content=deepcopy(payload) if native else package(payload, targets)
        # Source indexes and old addressing stay in JSON, never extra dependency relations.
        if native and isinstance(content,dict):content['provenance']=source.provenance(file,pointer,**(provenance_extra or {}))
        elif not native and isinstance(content['payload'],dict):
            content['payload']['_migration_provenance']=source.provenance(file,pointer,**(provenance_extra or {}))
        event={'event_id':event_id,'event_type':kind,'type_name':key,'event_action':action,'content':content}
        row={'node_id':node,'object':obj,'event':event,'target_event_ids':list(targets)}
        self.events.append(row);self.by_id[event_id]=row
        self.mappings.append({'file':file,'pointer':pointer,'node_id':node,'object_id':obj['object_id'],'event_id':event_id,'event_action':action})
        return event_id

    def version(self,node,kind,key,payload,file,pointer,current):
        obj=workflow_object(kind,key)['object_id'];old=current.get(obj, [])
        result=self.add(node,kind,key,payload,file,pointer,'replace' if old else 'append',old)
        current[obj]=[result]
        return result

    def cancel(self,node,kind,key,file,pointer,current,reason):
        obj=workflow_object(kind,key)['object_id'];old=current.get(obj, [])
        if not old:raise ValueError('No adopted target for '+file+pointer)
        result=self.add(node,kind,key,reason,file,pointer,'cancel',old)
        current[obj]=[]
        return result

    def design_records(self):
        source=self.source;result={}
        for folder in sorted((source.root/'.system/backstage').glob('*')):
            branch=folder.name
            if branch not in source.paths:continue
            for f in sorted(folder.rglob('*.json')):
                value=load(f);rel=f.relative_to(source.root).as_posix()
                if f.name!='plan.json':
                    for i,record in enumerate(value.get('revisions', [])):
                        node=record['effective_at_node_id']
                        anchor=next(b['forked_from_node_id'] for b in source.branches if b['branch_id']==branch)
                        if node==anchor and source.all_nodes[node]['origin_branch_id']!=branch:node=source.first_private(branch,node)
                        payload={**deepcopy(record),'text':record['proposition']+'\n'+record.get('causal_mechanism','')}
                        if node in source.nodes:
                            result.setdefault(node,[]).append(('truth',record['truth_id'],payload,rel,'/revisions/'+str(i),record['effective_at_node_id']))
                    continue
                # Plans have multiple versions: process all history entries below.
                if f.name=='plan.json':
                    cumulative={}
                    for i,record in enumerate(value['history']):
                        cumulative.update(record['changes']);node=record['expected_head'];kind='plan'
                        if branch=='main' and branch not in source.paths:kind='legacy_plan_archive'
                        elif node==next(b['forked_from_node_id'] for b in source.branches if b['branch_id']==branch) and source.all_nodes[node]['origin_branch_id']!=branch:
                            node=source.first_private(branch,node)
                        if node in source.nodes:
                            payload={'text':'\n'.join(k+'：'+str(v) for k,v in cumulative.items()),**deepcopy(cumulative),
                                     'revision':record['revision'],'reason':record['reason'],'legacy_branch_id':branch}
                            result.setdefault(node,[]).append((kind,branch,payload,rel,'/history/'+str(i),record['expected_head']))
        return result

    def build(self):
        s=self.source
        for node in s.order:
            meta=s.nodes[node];parent=meta['creation_parent_id'];file='nodes/'+node+'/delta.json'
            current=deepcopy(self.versions.get(parent,{}))
            if meta['kind']=='root':
                self.states[node]=deepcopy(s.baseline)
                self.add(node,'story_identity','identity',{'story_id':s.story['id'],'title':s.story['title'],
                    'default_branch_id':self.default_branch},'story.json','/identity',native=True)
                for key,value in sorted(s.settings().items()):
                    self.add(node,'story_setting',key,value,'story.json','/'+key,native=True)
                text=s.baseline.get('author_notes','')
                if text:self.version(node,'author_notes','story',{'text':text},'nodes/'+node+'/snapshot.json','/author_notes',current)
                if s.baseline.get('director'):
                    self.version(node,'director_state','story',deepcopy(s.baseline['director']),
                                 'nodes/'+node+'/snapshot.json','/director',current)
            else:
                before=self.states[parent];delta=s.deltas[node]
                after=apply_delta(before,delta,node);self.states[node]=after
                self.add(node,'narrative',node,{'literary_text':s.prose[node]},'nodes/'+node+'/narrative.md','',native=True)
                self.add(node,'display_metadata',node,deepcopy(delta['scene']),file,'/scene',native=True)
                inp=deepcopy(s.inputs[node])
                self.add(node,'user_input',node,inp,'nodes/'+node+'/input.json','',native=True)
                additions=[('/facts_add/'+str(i),f) for i,f in enumerate(delta.get('facts_add',[]))]
                additions += [('/facts_replace/'+str(i)+'/new_fact',r['new_fact']) for i,r in enumerate(delta.get('facts_replace',[]))]
                for pointer,fact in additions:
                    key=fact['id'];value=after['world_facts'][key]
                    if key in before['world_facts'] and before['world_facts'][key]['claim']==value['claim']:continue
                    self.version(node,'world_fact',key,{**deepcopy(value),'text':value['claim']},file,pointer,current)
                supers=[('/facts_supersede/'+str(i),r) for i,r in enumerate(delta.get('facts_supersede',[]))]
                supers += [('/facts_replace/'+str(i)+'/cancel',r) for i,r in enumerate(delta.get('facts_replace',[]))]
                for pointer,record in supers:self.cancel(node,'world_fact',record['id'],file,pointer,current,deepcopy(record))
                for i,patch in enumerate(delta.get('character_upserts',[])):
                    key=patch['id'];profile=deepcopy(after['characters'][key]);profile['character_id']=key
                    if key=='player':profile['is_protagonist']=True
                    self.version(node,'role_profile',key,profile,file,'/character_upserts/'+str(i),current)
                added=after['character_memories'][len(before['character_memories']):]
                for i,memory in enumerate(added):
                    self.add(node,'role_memory',memory['character_id'],deepcopy(memory),file,'/memories_add/'+str(i))
                for key in delta.get('relationships',{}):
                    value=deepcopy(after['relationships'][key]);value['id']=key
                    value['character_ids']=list(dict.fromkeys(value.get('characters',value.get('participants',[]))))
                    value.setdefault('text',value.get('description',value.get('relation',json.dumps(value,ensure_ascii=False))))
                    self.version(node,'relationship',key,value,file,'/relationships/'+key,current)
                for kind,prefix,state_key in [('thread','threads','open_threads'),('historical_trace','historical_traces','historical_traces')]:
                    add_key=prefix+('_open' if kind=='thread' else '_add')
                    for field in (add_key,prefix+'_update'):
                        for i,patch in enumerate(delta.get(field,[])):
                            key=patch['id'];value=deepcopy(after[state_key][key])
                            self.version(node,kind,key,value,file,'/'+field+'/'+str(i),current)
                    for i,key in enumerate(delta.get(prefix+'_close',[])):
                        self.cancel(node,kind,key,file,'/'+prefix+'_close/'+str(i),current,
                                    {'reason':'Legacy record closed in this scene','closed_record':deepcopy(after[state_key][key])})
                if 'author_notes' in delta:
                    self.version(node,'author_notes','story',{'text':delta['author_notes']},file,'/author_notes',current)
                if 'director_update' in delta:
                    self.version(node,'director_state','story',deepcopy(after['director']),file,'/director_update',current)
                handled={'scene','facts_add','facts_replace','facts_supersede','character_upserts','memories_add','relationships',
                         'threads_open','threads_update','threads_close','historical_traces_add','historical_traces_update',
                         'historical_traces_close','author_notes','director_update'}
                for key,value in delta.items():
                    if key not in handled:self.add(node,'legacy_scene_annotation',key,{'value':deepcopy(value)},file,'/'+key)
            self.add(node,'node_metadata',node,deepcopy(meta),'nodes/'+node+'/meta.json','',native=True)
            for kind,key,value,file,pointer,old_node in self.backend.get(node,[]):
                if kind=='legacy_plan_archive':self.add(node,kind,key,value,file,pointer,provenance_extra={'legacy_anchor':old_node})
                else:
                    self.version(node,kind,key,value,file,pointer,current)
                    self.by_id[stable(s.story['id'],file,pointer)]['event']['content']['payload']['_migration_provenance']['legacy_anchor']=old_node
            for file,index,record in self.notebooks.get(node,[]):
                text=self.states[node].get('author_notes','')+'\n\n'+record['text']
                self.version(node,'author_notes','story',{'text':text,'notebook_entry':deepcopy(record)},file,'/entries/'+str(index),current)
            self.versions[node]=current
        self.packages()
        self.capsules()
        return {'source':str(s.root),'story_id':s.story['id'],'title':s.story['title'],'default_branch_id':self.default_branch,
                'node_order':s.order,'nodes':s.nodes,'branches':s.branches,'events':self.events,'mappings':self.mappings,
                'source_hashes':s.hashes,'excluded_node_ids':sorted(set(s.all_nodes)-set(s.nodes)),
                'deferred':self.deferred,'excluded':self.excluded}

    def source_indexes(self,node,value):
        """Resolve navigation/prose/record identity against this node's selected prefix."""
        allowed=set(self.source.path(node));ids=[]
        def visit(v):
            if isinstance(v,dict):
                record_id=v.get('id');origin=v.get('node_id',v.get('source_node_id'))
                if origin in allowed:
                    candidate=stable(self.source.story['id'],'nodes/'+origin+'/narrative.md','')
                    if candidate in self.by_id:ids.append(candidate)
                if record_id:
                    for kind in ('world_fact','role_profile','thread','historical_trace'):
                        obj=workflow_object(kind,record_id)['object_id']
                        ids.extend(self.versions[node].get(obj,[]))
                for item in v.values():visit(item)
            elif isinstance(v,list):
                for item in v:visit(item)
        visit(value)
        return list(dict.fromkeys(ids))

    def packages(self):
        s=self.source;files=[]
        files += list((s.root/'.system/exchanges').glob('*/messages/*.json'))
        for folder in ('.system/scene-runs','.system/revisions'):
            for name in ('request.json','reply.json','finalize.json'):
                files += list((s.root/folder).glob('*/'+name))
        used={};message_ids={}
        for f in sorted(files):
            value=load(f);rel=f.relative_to(s.root).as_posix()
            branch=value.get('scope',{}).get('branch_id',value.get('branch_id'))
            if branch and branch not in s.paths and not any(m['origin_branch_id']==branch and m['kind']=='scene' for m in s.nodes.values()):
                self.excluded.append({'file':rel,'reason':'Excluded branch'});continue
            node,evidence=s.bind(value,rel)
            if node is None:
                run=f.parent/'run.json'
                if run.is_file() and load(run).get('node_id') in s.all_nodes and load(run).get('node_id') not in s.nodes:
                    self.excluded.append({'file':rel,'reason':'Excluded branch run'});continue
                self.deferred.append({'file':rel,'reason':evidence});continue
            fingerprint=digest(json.dumps(value,ensure_ascii=False,sort_keys=True).encode('utf8'))
            if fingerprint in used:
                self.mappings.append({'file':rel,'pointer':'','node_id':node,'event_id':used[fingerprint],'duplicate':True});continue
            kind=value.get('kind')
            event_type=('director_archive' if f.name=='finalize.json' else 'director_packet' if kind=='scene.request'
                        else 'author_packet' if kind in ('author.reply','dialogue.turn') and 'literary_text' in value else 'legacy_creative_record')
            clean=deepcopy(value);body=clean.pop('literary_text',None)
            refs=self.source_indexes(node,clean)
            if event_type=='director_archive':
                clean.pop('delta',None)
                refs.extend(m['event_id'] for m in self.mappings if m['node_id']==node and m['file']=='nodes/'+node+'/delta.json')
            if body is not None:
                narrative=stable(s.story['id'],'nodes/'+node+'/narrative.md','')
                if body==s.prose[node]:clean['narrative_event_id']=narrative;refs.append(narrative)
                elif body in s.prose[node]:
                    start=s.prose[node].index(body);clean['narrative_event_id']=narrative
                    clean['published_text_range']={'start':start,'end':start+len(body)};refs.append(narrative)
                else:
                    candidate=self.add(node,'narrative_candidate',clean.get('message_id',f.parent.name),{'literary_text':body},rel,'/literary_text',native=True)
                    clean['candidate_event_id']=candidate;refs.append(candidate)
            # Previous complete prose is a source index, never a second prose copy.
            now=clean.get('story_now',{})
            if isinstance(now,dict) and 'previous_scene_prose' in now:
                text=now.pop('previous_scene_prose')
                matches=[n for n in s.path(node) if text and s.prose[n]==text]
                if matches:now['previous_narrative_event_id']=stable(s.story['id'],'nodes/'+matches[-1]+'/narrative.md','')
                elif text:now['legacy_previous_prose_unresolved']=True
            packet={'legacy':clean,'event_ids':list(dict.fromkeys(refs)),
                    'raw_input_event_ids':[stable(s.story['id'],'nodes/'+node+'/input.json','')] if node!=s.root_id else [],
                    'interpreted_intent':s.inputs[node].get('interpreted_intent',''),
                    'historical_import':True}
            eid=self.add(node,event_type,clean.get('message_id',f.parent.name),packet,rel,'',native=True,
                         provenance_extra={'ownership_evidence':evidence})
            used[fingerprint]=eid
            if value.get('message_id'):message_ids[value['message_id']]=eid
        for row in self.events:
            if row['event']['event_type'] in ('director_packet','author_packet'):
                reply=row['event']['content'].get('legacy',{}).get('reply_to')
                if reply in message_ids:row['event']['content']['source_packet_event_id']=message_ids[reply]
        # Completed dialogue drafts are evidence, not restored running sessions.
        for f in sorted((s.root/'.system/drafts').glob('*.json')):
            value=load(f);rel=f.relative_to(s.root).as_posix()
            node,evidence=s.bind(value,rel)
            if not node:self.deferred.append({'file':rel,'reason':evidence});continue
            fragments=[]
            for i,fragment in enumerate(value.get('fragments',[])):
                text=fragment.get('text','')
                if text and text in s.prose[node]:
                    start=s.prose[node].index(text);fragments.append({**{k:v for k,v in fragment.items() if k!='text'},'range':{'start':start,'end':start+len(text)}})
                else:
                    # A historical transcript can contain user/prose/technical frontmatter.
                    # Preserve that distinct source document in SQLite without inventing turns
                    # or selecting it as a second authoritative narrative.
                    fragments.append({**deepcopy(fragment),'representation':'original-historical-transcript'})
            self.add(node,'legacy_dialogue_record',f.stem,{'status':value.get('status'),'fragments':fragments,
                     'narrative_event_id':stable(s.story['id'],'nodes/'+node+'/narrative.md','')},rel,'',native=True)

    def capsules(self):
        s=self.source;used=set()
        for f in sorted((s.root/'indices/capsules').rglob('*.json')):
            value=load(f);rel=f.relative_to(s.root).as_posix();nodes=[x['node_id'] for x in value.get('source_nodes',[])]
            if not nodes or not set(nodes)<=set(s.nodes):continue
            valid=all(digest((s.root/'nodes'/x['node_id']/'manifest.json').read_bytes())==x['manifest_sha256'] for x in value['source_nodes'])
            if not valid:self.excluded.append({'file':rel,'reason':'Stale derived capsule source fingerprint'});continue
            node=nodes[-1];branch=value.get('branch_id')
            if branch in s.paths and s.nodes[node]['origin_branch_id']!=branch:
                node=s.first_private(branch,node)
            signature=digest(json.dumps([nodes,value.get('summary'),value.get('anchors')],ensure_ascii=False,sort_keys=True).encode('utf8'))
            if signature in used:continue
            used.add(signature)
            payload=deepcopy(value);payload['source_event_ids']=[stable(s.story['id'],'nodes/'+n+'/narrative.md','') for n in nodes]
            self.add(node,'legacy_stage_summary',signature,payload,rel,'',native=True)


def plan(source, branch_ids, default_branch):
    return Planner(source,branch_ids,default_branch).build()
