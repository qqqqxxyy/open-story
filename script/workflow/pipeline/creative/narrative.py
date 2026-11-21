"""Resolve authoritative prose without storing a second copy of dialogue."""
from script.util.errors import ContractError


def resolve(records, event_id):
    visiting = set()

    def text(key):
        if key in visiting or key not in records:
            raise ContractError('INVALID_NARRATIVE_REFERENCE', 'Missing or cyclic narrative reference: '+key)
        visiting.add(key)
        content = records[key]['content']
        if not isinstance(content, dict):
            raise ContractError('INVALID_NARRATIVE_REFERENCE', 'Narrative content must be an object')
        if isinstance(content.get('literary_text'), str):
            value = content['literary_text']
        elif isinstance(content.get('fragment_event_ids'), list) and content['fragment_event_ids']:
            value = '\n\n'.join(text(item) for item in content['fragment_event_ids'])
        else:
            raise ContractError('INVALID_NARRATIVE_REFERENCE', 'Narrative needs prose or ordered fragments')
        visiting.remove(key)
        return value

    return text(event_id)


def read(repository, node, seq_max=None):
    if not node['narrative_event_id']:
        return None
    records={}
    pending=[node['narrative_event_id']]
    while pending:
        rows=repository.source_records(node['node_id'],event_ids=pending,seq_max=seq_max)
        found={row['event']['event_id']:row['event'] for row in rows}
        if set(pending)-found.keys():
            raise ContractError('INVALID_NARRATIVE_REFERENCE','Prose sources are missing or outside the selected path')
        records.update(found)
        pending=list(dict.fromkeys(key for event in found.values() if isinstance(event['content'],dict)
                                   for key in event['content'].get('fragment_event_ids',[]) if key not in records))
    return resolve(records,node['narrative_event_id'])
