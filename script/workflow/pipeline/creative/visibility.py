"""Default narrative visibility is adopted prose, not every stored revision."""
from script.util.errors import ContractError

PROSE_KINDS={'narrative','author_reply','dialogue_fragment','author_packet','display_metadata','scene_summary'}


def rows(repository,records):
    if not records:return records
    ids=list(dict.fromkeys(r['node_id'] for r in records))
    nodes={n['node_id']:n for n in repository.records('node',{'node_id':ids})}
    selected={n['narrative_event_id'] for n in nodes.values() if n['state']=='active'}
    selected.update(n['summary_event_id'] for n in nodes.values() if n['state']=='active')
    # A selected composite may recursively reference dialogue fragments.
    pending=[i for i in selected if i]
    known={r['event']['event_id']:r['event'] for r in records}
    while pending:
        missing=[i for i in pending if i not in known]
        if missing:known.update({e['event_id']:e for e in repository.records('event',{'event_id':missing})})
        next_ids=set(i for key in pending for i in known.get(key,{}).get('content',{}).get('fragment_event_ids',[]))
        pending=list(next_ids-selected);selected.update(next_ids)
    result=[]
    for r in records:
        e=r['event'];node=nodes[r['node_id']]
        if e['event_type'] not in PROSE_KINDS:result.append(r);continue
        if node['state']!='active':continue
        if e['event_id'] in selected or (e['event_type']=='author_packet' and
             e['content'].get('narrative_event_id')==node['narrative_event_id']):result.append(r)
    return result


def require_adopted(repository,node_ids):
    nodes=repository.records('node',{'node_id':list(node_ids)})
    if len(nodes)!=len(set(node_ids)) or any(n['state']!='active' for n in nodes):
        raise ContractError('DRAFT_NOT_ADOPTED','Normal history reads only adopted prose; recover the current draft by author packet ID')


def maintenance_rows(repository,ctx,records):
    """Frozen job sources plus records produced by this maintenance job itself."""
    from .common import identifier
    receipt=repository.get('event',identifier('archival',ctx['node_id']))
    produced=set(receipt['content']['event_ids']) if receipt else set()
    if receipt:produced.add(receipt['event_id'])
    return [row for row in records if row['node_id']!=ctx['node_id'] or row['event']['seq']<=ctx['history_event_seq']
        or row['event']['event_id'] in produced
        or (row['event']['event_action']=='summarize' and
            row['event']['content'].get('_capsule',{}).get('maintenance_job_id')==ctx['maintenance_job_id'])]
