"""Business-facing source mapping over composed storage queries; no SQL."""
from script.util.errors import ContractError


class CreativeRepository:
    def __init__(self, repository):
        self.repository = repository

    def sources(self, end_node_id, current_node_id=None, event_ids=None,
                object_ids=None, event_types=None, seq_max=None):
        return self.repository.source_records(end_node_id, current_node_id=current_node_id,
            event_ids=event_ids, object_ids=object_ids, event_types=event_types, seq_max=seq_max)

    def local(self, node_id, event_types=None):
        return self.sources(None, current_node_id=node_id, event_types=event_types)

    def referenced(self, context, event_ids):
        ids = list(dict.fromkeys(event_ids))
        rows = self.sources(context['history_node_id'], context['node_id'], event_ids=ids,
                            seq_max=context['history_event_seq']) if ids else []
        by_id = {row['event']['event_id']: row for row in rows}
        missing = set(ids) - by_id.keys()
        if missing:
            raise ContractError('SOURCE_NOT_VISIBLE', 'Missing or outside creative scope: ' + ', '.join(sorted(missing)))
        return [by_id[event_id] for event_id in ids]
