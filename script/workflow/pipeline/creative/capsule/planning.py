"""Deterministic incremental batches and repair batches over capsule projections."""
from .state import metadata, latest_successor


def batch(level, sources, supersedes=(), reason='threshold'):
    return {'level': level, 'reason': reason, 'source_event_ids': list(sources),
            'supersedes_capsule_event_ids': list(supersedes)}


def plan(view, policy):
    capsules = view['capsules']
    levels = {level: [key for key, row in capsules.items() if metadata(row['event'])['level'] == level]
              for level in (1, 2)}
    used_content = set().union(*(view['coverage'][key] for key in levels[1]))
    pending = [key for key in view['contents'] if key not in used_content]
    jobs = {1: [], 2: []}
    blocked = []
    for key in levels[1]:
        if view['statuses'][key]['status'] == 'stale':
            sources = [source for source in metadata(capsules[key]['event'])['source_event_ids']
                       if source in view['contents']]
            jobs[1].append(batch(1, sources, [key], 'stale'))
    width = policy['level_1_events']
    for offset in range(0, len(pending)-width+1, width):
        jobs[1].append(batch(1, pending[offset:offset+width]))
    used_level_1 = set()
    for key in levels[2]:
        sources = [latest_successor(view, source) for source in metadata(capsules[key]['event'])['source_event_ids']]
        used_level_1.update(sources)
        if view['statuses'][key]['status'] != 'stale':
            continue
        unavailable = [source for source in sources if source not in view['statuses'] or view['statuses'][source]['status'] != 'valid']
        if unavailable:
            blocked.extend(unavailable)
        else:
            jobs[2].append(batch(2, sources, [key], 'stale'))
    pending_1 = [key for key in levels[1] if view['statuses'][key]['status'] == 'valid'
                 and view['coverage'][key] and key not in used_level_1]
    pending_1.sort(key=lambda key: view['order'][key])
    width = policy['level_2_capsules']
    for offset in range(0, len(pending_1)-width+1, width):
        jobs[2].append(batch(2, pending_1[offset:offset+width]))
    return {'jobs': jobs, 'pending_counts': {1: len(pending), 2: len(pending_1)},
            'blocked': list(dict.fromkeys(blocked))}


def allocate(plans, budget):
    """One batch per object per pass; expose remaining work without expanding it."""
    chosen = {(key, level): [] for key in plans for level in (1, 2)}
    queues = [(key, level, list(value['jobs'][level])) for level in (1, 2) for key, value in plans.items()]
    while budget and any(queue for _, _, queue in queues):
        for key, level, queue in queues:
            if queue and budget:
                chosen[key, level].append(queue.pop(0))
                budget -= 1
    return chosen
