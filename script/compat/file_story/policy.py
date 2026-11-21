"""Explicit source-specific migration choices, outside normal creative workflows."""
from copy import deepcopy
from pathlib import Path
import json
from .inventory import load, stable, digest
from script.workflow.pipeline.creative.actions import package, unpack


def apply_policy(original, policy, legacy_source=None):
    """Transform a read-only core plan; preserve event IDs, owners and action targets."""
    result = deepcopy(original)
    if result['story_id'] != policy['story_id']:
        raise ValueError('Policy belongs to a different source story')
    topics = policy.get('fact_topics', [])
    archived = set(policy.get('archive_fact_ids', []))
    topic_by_fact = {}
    if len(topics) > policy.get('max_fact_topics', 20):
        raise ValueError('Fact topic limit exceeded')
    for topic in topics:
        for key in topic['fact_ids']:
            if key in topic_by_fact or key in archived:
                raise ValueError('Each old fact needs exactly one disposition: '+key)
            topic_by_fact[key] = topic
    old_facts = {row['object']['object_key'] for row in result['events']
                 if row['event']['event_type'] == 'world_fact'}
    if topics or archived:
        if old_facts != set(topic_by_fact) | archived:
            raise ValueError('Policy must cover all source facts exactly')
    for row in result['events']:
        event = row['event']
        if event['event_type'] == 'world_fact':
            key = row['object']['object_key']
            if key in archived:
                if event['event_action'] != 'append' or row['target_event_ids']:
                    raise ValueError('Historical creative notes require an independent content record')
                row['object'] = {'object_id': 'author_notes_story', 'object_type': 'author_notes',
                                 'object_key': 'story', 'name': 'story'}
                event['event_type'] = 'author_notes'
                content, _ = unpack(event['content'])
                content.update({'historical_only': True, 'record_kind': 'legacy_rule_change',
                                'applies_to': 'legacy_runtime_only'})
            elif key in topic_by_fact:
                topic = topic_by_fact[key]
                row['object'] = {'object_id': 'world_fact_'+topic['key'], 'object_type': 'world_fact',
                                 'object_key': topic['key'], 'name': topic['name']}
        if event['event_type'] == 'node_metadata':
            for key in policy.get('strip_node_metadata_fields', []):
                event['content'].pop(key, None)

    supplement = policy.get('legacy')
    if supplement:
        if legacy_source is None:
            raise ValueError('This policy requires an explicit legacy source')
        root = Path(legacy_source).resolve()
        source_id = 'legacy-v3'
        files = {supplement['commit_file'], supplement['director_file']}
        hashes = {name: digest((root/name).read_bytes()) for name in files}
        result.setdefault('supplemental_sources', {})[source_id] = {'root': str(root), 'hashes': hashes}
        commits = {}
        for number, line in enumerate((root/supplement['commit_file']).read_text(encoding='utf-8-sig').splitlines(), 1):
            if not line.strip():
                continue
            commit = json.loads(line)
            if commit['turn_id'] in commits:
                raise ValueError('Duplicate legacy turn ID')
            commits[commit['turn_id']] = (number, commit)
        inputs = {row['node_id']: row['event']['content'] for row in result['events']
                  if row['event']['event_type'] == 'user_input'}
        for row in result['events']:
            if row['event']['event_type'] != 'node_metadata' or row['node_id'] not in inputs:
                continue
            value = inputs[row['node_id']]
            number, commit = commits[value['turn_id']]
            if commit['raw_player_input'] != value.get('raw_player_input', ''):
                raise ValueError('Legacy input differs at '+row['node_id'])
            row['event']['content']['committed_at'] = commit['committed_at']
            row['event']['content']['provenance']['legacy_commit'] = {
                'source_id': source_id, 'source_file': supplement['commit_file'],
                'json_pointer': '/committed_at', 'line_number': number,
                'source_sha256': hashes[supplement['commit_file']]}

        snapshot = load(root/supplement['director_file'])['director']
        node_id = supplement['director_node_id']
        if node_id not in result['nodes']:
            raise ValueError('Director snapshot owner is not retained')
        ancestors = set()
        cursor = node_id
        while cursor:
            ancestors.add(cursor)
            cursor = result['nodes'][cursor]['creation_parent_id']
        prior = [row['event']['event_id'] for row in result['events']
                 if row['node_id'] in ancestors and row['event']['event_type'] == 'director_state'
                 and row['event']['event_action'] in ('append', 'replace')]
        controlled = {target for row in result['events'] if row['node_id'] in ancestors
                      for target in row['target_event_ids']}
        targets = [key for key in prior if key not in controlled]
        pointer = '/director'
        source_file = supplement['director_file']
        event_id = stable(result['story_id'], source_id+'/'+source_file, pointer)
        provenance = {'source_id': source_id, 'source_file': source_file, 'json_pointer': pointer,
                      'source_sha256': hashes[source_file], 'historical_snapshot': True}
        payload = {**deepcopy(snapshot), '_migration_provenance': provenance}
        row = {'node_id': node_id, 'object': {'object_id': 'director_state_story',
               'object_type': 'director_state', 'object_key': 'story', 'name': 'story'},
               'event': {'event_id': event_id, 'event_type': 'director_state', 'type_name': 'story',
                         'event_action': 'replace' if targets else 'append',
                         'content': package(payload, targets)}, 'target_event_ids': targets}
        insertion = max(index for index, old in enumerate(result['events']) if old['node_id'] == node_id)+1
        result['events'].insert(insertion, row)
        result['mappings'].append({'file': source_file, 'source_id': source_id, 'pointer': pointer,
                                  'node_id': node_id, 'object_id': row['object']['object_id'],
                                  'event_id': event_id, 'event_action': row['event']['event_action']})

    by_id = {row['event']['event_id']: row for row in result['events']}
    for row in result['events']:
        if any(by_id[target]['object']['object_id'] != row['object']['object_id']
               for target in row['target_event_ids']):
            raise ValueError('Policy changed an action target to a different object')
    for mapping in result['mappings']:
        row = by_id[mapping['event_id']]
        mapping['object_id'] = row['object']['object_id']
    result['migration_policy'] = {'fact_topic_count': len(topics), 'archived_fact_ids': sorted(archived),
                                  'stripped_metadata_fields': policy.get('strip_node_metadata_fields', []),
                                  'preserved_committed_at': bool(supplement),
                                  'branch_lifecycle': 'open'}
    return result
