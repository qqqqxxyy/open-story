"""Bounded, version-pinned prose pages over batched scoped source queries."""
import base64
import json
from hashlib import sha256
from script.util.errors import ContractError
from script.util.contracts import validate
from script.util.runtime import WORKFLOW
from script.workflow.data.creative import CreativeRepository
from .common import settings, scoped_sources
from .narrative import resolve


def scope_key(ctx):
    fields = {key: ctx[key] for key in
              ('node_id', 'branch_id', 'history_node_id', 'history_event_seq')}
    return sha256(json.dumps(fields, sort_keys=True).encode('utf-8')).hexdigest()


def encode_cursor(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii')


def decode_cursor(value):
    try:
        result = json.loads(base64.urlsafe_b64decode(value).decode('utf-8'))
        validate(result, 'prose_cursor', WORKFLOW)
        return result
    except Exception as exc:
        raise ContractError('INVALID_ARGUMENT', 'Use the next_cursor returned by the prose page') from exc


def selections(repository, ctx, node_ids):
    from .visibility import require_adopted
    require_adopted(repository,node_ids)
    allowed = set(repository.ancestor_path(ctx['history_node_id'])) | {ctx['node_id']}
    if not set(node_ids) <= allowed:
        raise ContractError('SOURCE_NOT_VISIBLE', 'Requested prose is outside the creative path')
    nodes = {node['node_id']: node for node in repository.records('node', {'node_id': node_ids})}
    versions = []
    for node_id in node_ids:
        version = nodes[node_id]['narrative_event_id']
        if node_id == ctx['history_node_id']:
            version = ctx.get('previous_narrative_event_id', version)
        versions.append(version)
    return versions


def texts(repository, ctx, node_ids, versions):
    source = scoped_sources(repository)
    records = {}
    pending = list(dict.fromkeys(key for key in versions if key))
    owners = {}
    while pending:
        rows = source.referenced(ctx, pending)
        for row in rows:
            event = row['event']
            records[event['event_id']] = event
            owners[event['event_id']] = row['node_id']
        pending = list(dict.fromkeys(key for row in rows
                       for key in row['event']['content'].get('fragment_event_ids', [])
                       if key not in records))
    result = []
    for node_id, event_id in zip(node_ids, versions):
        if event_id and owners[event_id] != node_id:
            raise ContractError('SOURCE_NOT_VISIBLE', 'Prose version is owned by another node')
        result.append(resolve(records, event_id) if event_id else '')
    return result


def read_page(repository, ctx, params):
    cursor = params.get('cursor')
    if cursor:
        state = decode_cursor(cursor)
        if state['scope_key'] != scope_key(ctx):
            raise ContractError('SOURCE_NOT_VISIBLE', 'Prose cursor belongs to another creative scope')
        node_ids = state['node_ids']
        if params.get('source_node_ids', node_ids) != node_ids:
            raise ContractError('INVALID_ARGUMENT', 'Keep the node list associated with next_cursor')
        versions = state['narrative_event_ids']
    else:
        node_ids = params['source_node_ids']
        versions = selections(repository, ctx, node_ids)
        state = {'scope_key': scope_key(ctx), 'node_ids': node_ids,
                 'narrative_event_ids': versions, 'node_index': 0, 'character_offset': 0}
    if len(versions) != len(node_ids) or state['node_index'] >= len(node_ids):
        raise ContractError('INVALID_ARGUMENT', 'Prose cursor has no remaining node')
    maximum = params.get('max_text_chars', settings()['reading']['prose_page_characters'])
    index = state['node_index']
    offset = state['character_offset']
    remaining_texts = texts(repository, ctx, node_ids[index:], versions[index:])
    remaining = maximum
    chunks = []
    for text in remaining_texts:
        if remaining == 0:
            break
        if offset > len(text):
            raise ContractError('INVALID_ARGUMENT', 'Prose cursor is beyond the selected version')
        end = min(len(text), offset + remaining)
        if end < len(text):
            paragraph = text.rfind('\n\n', offset, end)
            if paragraph > offset and paragraph + 2 <= end:
                end = paragraph + 2
        value = text[offset:end]
        complete = end == len(text)
        chunks.append({'node_id': node_ids[index], 'narrative_event_id': versions[index],
                       'literary_text': value, 'text_start': offset, 'text_end': end,
                       'total_characters': len(text), 'node_complete': complete})
        remaining -= len(value)
        if complete:
            index += 1
            offset = 0
        else:
            offset = end
            break
    complete = index == len(node_ids)
    next_cursor = None if complete else encode_cursor(
        {**state, 'node_index': index, 'character_offset': offset})
    page = {'max_text_chars': maximum, 'returned_characters': maximum - remaining,
            'returned_node_count': len(chunks), 'total_node_count': len(node_ids),
            'complete': complete, 'next_cursor': next_cursor}
    return {'scope': ctx, 'view': 'prose', 'page': page, 'sources': [],
            'total': len(node_ids), 'next_offset': None, 'narratives': chunks}
