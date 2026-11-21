"""Object-scoped summary projections; no IO, mutation or literary inference."""
from ..common import settings
from ..actions import unpack


def policy(object_type):
    config = settings()['capsule']
    kind = next((name for name, definition in settings()['categories'].items()
                 if object_type == name or object_type in definition['event_types']), None)
    value = {**config['defaults'], **config['kinds'].get(kind, {})}
    return {**value, 'enabled': bool(value['enabled'] and kind is not None), 'kind': kind}


def metadata(event):
    return event['content']['_capsule']


def project(rows):
    """Compute branch-local validity, version succession and roll-up coverage."""
    by_id = {row['event']['event_id']: row for row in rows}
    active = [row for row in rows if row['event']['state'] == 'active']
    excluded = set()
    for row in active:
        event = row['event']
        if event['event_action'] in ('replace', 'cancel'):
            excluded.update(unpack(event['content'])[1])
    contents = {row['event']['event_id']: row for row in active
                if row['event']['event_action'] in ('append', 'replace')
                and row['event']['event_id'] not in excluded}
    capsules = {row['event']['event_id']: row for row in active
                if row['event']['event_action'] == 'summarize'}
    successor = {}
    for key, row in capsules.items():
        for old in metadata(row['event'])['supersedes_capsule_event_ids']:
            successor[old] = key
    statuses = {}
    for level in (1, 2):
        for key, row in capsules.items():
            meta = metadata(row['event'])
            if meta['level'] != level:
                continue
            missing = []
            obsolete = []
            for source in meta['source_event_ids']:
                origin = by_id.get(source)
                if origin is None:
                    missing.append(source)
                elif level == 1:
                    if source not in contents:
                        obsolete.append(source)
                elif source not in statuses or metadata(origin['event'])['level'] != 1 or statuses[source]['status'] != 'valid':
                    obsolete.append(source)
            status = 'superseded' if key in successor else 'stale' if missing or obsolete else 'valid'
            statuses[key] = {'status': status, 'missing_source_ids': missing, 'obsolete_source_ids': obsolete}
    coverage = {}
    for level in (1, 2):
        for key, row in capsules.items():
            meta = metadata(row['event'])
            if meta['level'] != level:
                continue
            coverage[key] = (set(meta['source_event_ids']) if level == 1 else
                             set().union(*(coverage.get(source, set()) for source in meta['source_event_ids'])))
    covered_by = {key: [] for key in capsules}
    for key, row in capsules.items():
        if metadata(row['event'])['level'] == 2 and statuses[key]['status'] == 'valid':
            for source in metadata(row['event'])['source_event_ids']:
                if source in covered_by:
                    covered_by[source].append(key)
    views = [{**row, 'capsule_status': statuses[key]['status'], 'covered_by': covered_by[key],
              'covered_event_count': len(coverage[key]),
              'missing_source_ids': statuses[key]['missing_source_ids'],
              'obsolete_source_ids': statuses[key]['obsolete_source_ids']}
             for key, row in capsules.items()]
    overview = [row for row in views if row['capsule_status'] == 'valid' and row['covered_event_count']
                and (metadata(row['event'])['level'] == 2 or not row['covered_by'])]
    positions = {key: index for index, key in enumerate(by_id)}
    order = {key: min((positions.get(source, len(positions)) for source in sources), default=len(positions))
             for key, sources in coverage.items()}
    overview.sort(key=lambda row: order[row['event']['event_id']])
    return {'rows': by_id, 'contents': contents, 'capsules': capsules, 'statuses': statuses, 'order': order,
            'coverage': coverage, 'successor': successor, 'views': views, 'overview': overview}


def latest_successor(view, key):
    while key in view['successor']:
        key = view['successor'][key]
    return key


def groups(rows):
    result = {}
    for row in rows:
        result.setdefault(row['object_id'], []).append(row)
    return result
