"""Read-only scoped prose and views; never create a scene to inspect history."""
import re
from .story import Operations
from .creative.narrative import resolve
from .creative.projection import project


def scope(repository, params):
    if params.get('scene_node_id'):
        from .creative.common import context
        ctx=context(repository,params['scene_node_id'],params.get('branch_id'))
        return {'branch_id':ctx['branch_id'],'at_node_id':ctx['history_node_id'],
                'seq_max':ctx['history_event_seq'],'scene_node_id':ctx['node_id'],
                'previous_narrative_event_id':ctx.get('previous_narrative_event_id'),
                'previous_summary_event_id':ctx.get('previous_summary_event_id')}
    result=Operations(repository)._scope(params['branch_id'],params.get('at_node_id'))
    return {**result,'seq_max':None}


def inspect(repository, params):
    fixed=scope(repository,params)
    rows=repository.source_records(fixed['at_node_id'],seq_max=fixed['seq_max'])
    return {'scope':fixed,'projection':project(rows),'source_count':len(rows)}


def material(repository, fixed):
    allowed=repository.ancestor_path(fixed['at_node_id'])
    nodes={node['node_id']:node for node in repository.records('node',{'node_id':allowed})}
    nodes={key:node for key,node in nodes.items() if node['state']=='active'}
    rows=repository.source_records(fixed['at_node_id'],seq_max=fixed['seq_max'])
    return nodes,{row['event']['event_id']:row['event'] for row in rows}


def prose(fixed, nodes, records, node_id, event_id=None):
    if node_id not in nodes:
        from script.util.errors import ContractError
        raise ContractError('SOURCE_NOT_VISIBLE','Historical node is outside scope')
    node=nodes[node_id]
    if fixed.get('scene_node_id') and node_id==fixed['at_node_id']:
        node={**node,'narrative_event_id':fixed['previous_narrative_event_id'],
              'summary_event_id':fixed['previous_summary_event_id']}
    if event_id:
        if event_id not in records:
            from script.util.errors import ContractError
            raise ContractError('SOURCE_NOT_VISIBLE','Prose version is outside scope')
        node={**node,'narrative_event_id':event_id}
    text=resolve(records,node['narrative_event_id']) if node['narrative_event_id'] else ''
    paragraphs=[{'paragraph_index':i,'text':part} for i,part in enumerate(re.split(r'\n\s*\n',text),1) if part.strip()]
    summary=records.get(node['summary_event_id'])
    return {'node_id':node_id,'narrative_event_id':node['narrative_event_id'],'literary_text':text,
            'summary':summary['content'].get('summary','') if summary else '', 'paragraphs':paragraphs}


def read_node(repository, params):
    fixed=scope(repository,params)
    if params.get('narrative_event_id') and repository.owner(params['narrative_event_id'])['node_id']!=params['node_id']:
        from script.util.errors import ContractError
        raise ContractError('SOURCE_NOT_VISIBLE','Prose version is owned by another node')
    nodes,records=material(repository,fixed)
    item=prose(fixed,nodes,records,params['node_id'],params.get('narrative_event_id'))
    view=params.get('view','prose')
    if view=='prose':item.pop('paragraphs')
    elif view=='paragraphs':item.pop('literary_text')
    return {'scope':fixed,'view':view,**item}


def list_scenes(repository, params):
    fixed=scope(repository,params)
    path=repository.ancestor_path(fixed['at_node_id'])
    nodes={node['node_id']:node for node in repository.records('node',{'node_id':path})}
    ordered=[nodes[key] for key in path if nodes[key]['node_type']=='scene' and nodes[key]['narrative_event_id'] and nodes[key]['state']=='active']
    if fixed.get('scene_node_id'):
        ordered=[{**node,'narrative_event_id':fixed['previous_narrative_event_id'],
                  'summary_event_id':fixed['previous_summary_event_id']} if node['node_id']==fixed['at_node_id'] else node for node in ordered]
    end=max(0,len(ordered)-params['offset']);start=max(0,end-params['limit'])
    page=ordered[start:end]
    ids=[node['summary_event_id'] for node in page if node['summary_event_id']]
    rows=repository.source_records(fixed['at_node_id'],event_ids=ids,seq_max=fixed['seq_max']) if ids else []
    records={row['event']['event_id']:row['event'] for row in rows}
    items=[]
    for index,node in enumerate(page,start+1):
        summary=records.get(node['summary_event_id'],{}).get('content',{})
        items.append({'node_id':node['node_id'],'predecessor_node_id':node['predecessor_node_id'],
            'narrative_event_id':node['narrative_event_id'],'summary_event_id':node['summary_event_id'],
            'title':summary.get('title','第 '+str(index)+' 幕'),'summary':summary.get('summary',''),
            'time':summary.get('time',''),'location':summary.get('location',''),
            'participants':summary.get('participants',[])})
    return {'scope':fixed,'items':items,'total':len(ordered),
            'next_offset':params['offset']+len(items) if start>0 else None}


def _matches(items, keyword, offset, limit):
    needle=keyword.casefold();matches=[]
    for item in items:
        for paragraph in item['paragraphs']:
            if needle in paragraph['text'].casefold():
                matches.append({'node_id':item['node_id'],'narrative_event_id':item['narrative_event_id'],
                    'field':'narrative','paragraph_index':paragraph['paragraph_index'],'snippet':paragraph['text']})
        if needle in item['summary'].casefold():
            matches.append({'node_id':item['node_id'],'narrative_event_id':item['narrative_event_id'],
                'field':'summary','paragraph_index':None,'snippet':item['summary']})
    return {'matches':matches[offset:offset+limit],'total':len(matches),
            'next_offset':offset+limit if offset+limit<len(matches) else None}


def search(repository, params):
    fixed=scope(repository,params)
    nodes,records=material(repository,fixed)
    items=[prose(fixed,nodes,records,node_id) for node_id,node in nodes.items() if node['node_type']!='root']
    if 'keyword' in params:
        return {'scope':fixed,**_matches(items,params['keyword'],params['offset'],params['limit'])}
    return {'scope':fixed,'results':[{'keyword':word,**_matches(items,word,params['offset'],params['limit'])}
                                   for word in params['keywords']]}
