"""Import only root and first scene, as individual content records, through operations."""
from pathlib import Path
import hashlib
import json
from script.util.contracts import ContractError as DataError


def read_json(path):return json.loads(path.read_text(encoding='utf8'))
def digest(raw):return hashlib.sha256(raw).hexdigest()


def import_sample(ops,source_story):
    source=Path(source_story).resolve()
    metadata=read_json(source/'story.json')
    root='node-root'
    scenes=[]
    for path in (source/'nodes').glob('*/meta.json'):
        node=read_json(path)
        if node.get('kind')=='scene' and node.get('creation_parent_id')==root and node.get('display_index')==1:
            scenes.append(node)
    if len(scenes)!=1:raise DataError('SAMPLE_AMBIGUOUS','This helper requires a unique first scene directly after root')
    first=scenes[0]['node_id']
    mappings=[];skipped=[]

    def raw(relative):
        return (source/relative).read_bytes()
    def parsed(relative):return json.loads(raw(relative).decode('utf8'))
    def add(node,event_type,key,content,file,pointer='',select_as=None):
        event_id='sample-'+digest((file+'#'+pointer).encode('utf8'))[:24]
        object_id=event_type+'_'+key
        result=ops.create_event({'node_id':node,'branch_id':'main','object':{'object_id':object_id,'object_type':event_type,'object_key':key,'name':key},
            'event':{'event_id':event_id,'event_type':event_type,'type_name':key,'content':content},
            **({'select_as':select_as} if select_as else {})})
        mappings.append({'file':file,'pointer':pointer,'event_id':event_id,'object_id':object_id,
                         'node_id':node,'event_type':event_type})
        return result

    list_categories={'character_upserts':'role_profile','facts_add':'world_fact','facts_replace':'fact_replacement',
        'facts_supersede':'fact_supersession','memories_add':'role_memory','threads_open':'thread',
        'threads_update':'thread_update','threads_close':'thread_close','historical_traces_add':'historical_trace',
        'historical_traces_update':'trace_update','historical_traces_close':'trace_close'}
    def key_for(category,value,index):
        if category=='role_memory':return value.get('character_id','unknown')
        if isinstance(value,dict):return str(value.get('id') or index)
        return str(value)
    def items(node,values,file):
        for field,value in values.items():
            pointer='/'+field
            if field=='scene':add(node,'scene_summary',node,value,file,pointer,'summary')
            elif field=='author_notes':add(node,'author_notes','story',value,file,pointer)
            elif field=='director_update':add(node,'director_state','story',value,file,pointer)
            elif field=='relationships':
                for key,record in value.items():add(node,'relationship',key,record,file,pointer+'/'+key.replace('~','~0').replace('/','~1'))
            elif field in list_categories:
                for index,record in enumerate(value):
                    category=list_categories[field];add(node,category,key_for(category,record,index),record,file,pointer+'/'+str(index))
            else:
                # Preserve new/unknown categories as explicit content, without teaching the backend their meaning.
                add(node,field,node,value,file,pointer)

    with ops.repository.transaction():
        if ops.repository.get('node',root) is None:
            ops.begin({'node_id':root,'node_type':'root','branch_id':'main'})
        for field,value in parsed('story.json').items():
            if field in ('version','created_at'):
                skipped.append('story.json#/'+field+' (technical metadata also present in source report)')
                continue
            add(root,'story_setting',field,value,'story.json','/'+field)
        root_meta=parsed('nodes/'+root+'/meta.json')
        add(root,'node_metadata',root,root_meta,'nodes/'+root+'/meta.json')
        snapshot_file='nodes/'+root+'/snapshot.json'
        snapshot=parsed(snapshot_file)
        for field,value in snapshot.items():
            if field in ('version','story_id','node_id','canon_revision_id') or value in ({},[],None):
                skipped.append(snapshot_file+'#/'+field+' (identity or empty baseline field)');continue
            if field=='author_notes':add(root,'author_notes','story',value,snapshot_file,'/'+field)
            elif field=='director':add(root,'director_state','story',value,snapshot_file,'/'+field)
            elif isinstance(value,dict):
                for key,record in value.items():add(root,field,key,record,snapshot_file,'/'+field+'/'+key)
            elif isinstance(value,list):
                for index,record in enumerate(value):add(root,field,key_for(field,record,index),record,snapshot_file,'/'+field+'/'+str(index))
            else:add(root,field,'story',value,snapshot_file,'/'+field)
        for filename in ('input.json','delta.json','narrative.md'):
            relative='nodes/'+root+'/'+filename
            if not (source/relative).exists():continue
            if filename=='narrative.md':
                text=raw(relative).decode('utf8')
                if text:add(root,'author_reply','root',{'literary_text':text,'provenance':{'kind':'existing_published_prose','original_author_reply_available':False}},relative,select_as='narrative')
                else:skipped.append(relative+' (empty root placeholder)')
            else:
                value=parsed(relative)
                if not value:skipped.append(relative+' (empty root placeholder)')
                elif filename=='input.json':add(root,'user_input','root',value,relative)
                else:items(root,value,relative)
        if ops.repository.require('node',root)['state']!='active':ops.publish(root)
        if ops.repository.get('node',first) is None:
            ops.begin({'node_id':first,'predecessor_id':root,'branch_id':'main'})
        add(first,'node_metadata',first,parsed('nodes/'+first+'/meta.json'),'nodes/'+first+'/meta.json')
        add(first,'user_input',first,parsed('nodes/'+first+'/input.json'),'nodes/'+first+'/input.json')
        narrative_file='nodes/'+first+'/narrative.md'
        prose=raw(narrative_file).decode('utf8')
        add(first,'author_reply','story',{'literary_text':prose,
            'provenance':{'kind':'existing_published_prose','original_author_reply_available':False}},narrative_file,select_as='narrative')
        delta_file='nodes/'+first+'/delta.json'
        items(first,parsed(delta_file),delta_file)
        if ops.repository.require('node',first)['state']!='active':ops.publish(first)
    return {'source_story_id':metadata['id'],'node_ids':[root,first],'mapped_events':len(mappings),
        'mappings':mappings,'skipped_empty_or_technical_fields':skipped,
        'limitations':['Only root and first scene imported; later branch histories and backstage are outside this sample.',
                      'Existing input provenance retained; original host author reply is absent, so published prose is labelled as such.'],
        'counts':ops.execute('database.info',{})['counts']}
