"""Configurable exact recall with an independent object-scoped capsule overview."""
import json
from script.workflow.data.creative import CreativeRepository
from .common import enabled, context, settings, get_path, messages, scoped_sources
from .projection import project, searchable, identity
from .narrative import read
from .diagnostics import selection_summary, complete_diagnostics


def grams(text):
    value = ''.join(character for character in text.casefold() if character.isalnum())
    return {value[index:index+width] for width in settings()['recall']['gram_widths']
            for index in range(max(0, len(value)-width+1))}


def score(row, query):
    return len(grams(searchable(row)) & query)


def ranked(rows, query, count, scores=None):
    scores = scores if scores is not None else {row['event']['event_id']: score(row, query) for row in rows}
    return sorted(rows, key=lambda row: (scores[row['event']['event_id']], row['event']['seq']), reverse=True)[:count]


def recent_related(rows, query, recent_limit, related_limit):
    recent = rows[-recent_limit:] if recent_limit else []
    recent_ids = {row['event']['event_id'] for row in recent}
    older = [row for row in rows if row['event']['event_id'] not in recent_ids and score(row, query)]
    related = ranked(older, query, related_limit)
    return recent, related


def base(repository, ctx):
    kinds=list(dict.fromkeys(kind for category in settings()['categories'].values() for kind in category['event_types']))
    return CreativeRepository(repository).sources(ctx['history_node_id'],event_types=kinds,seq_max=ctx['history_event_seq'])


def recall(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    rows = base(repository, ctx)
    projection = project(rows)
    cfg = settings()['recall']
    sources = CreativeRepository(repository)
    inputs = sources.referenced(ctx, ctx['raw_input_event_ids'])
    raw = '\n'.join(message['text'] for row in inputs for message in messages(row['event']['content']))
    previous = repository.require('node', ctx['history_node_id'])
    previous = {**previous,'narrative_event_id':ctx.get('previous_narrative_event_id',previous['narrative_event_id']),
                'summary_event_id':ctx.get('previous_summary_event_id',previous['summary_event_id'])}
    previous_text = read(repository, previous) or ''
    summary = repository.get('event', previous['summary_event_id']) if previous['summary_event_id'] else None
    participant_ids = summary['content'].get('participants', []) if summary and isinstance(summary['content'], dict) else []
    query_text = (raw[-cfg['input_characters']:]+' '+params.get('scene_need', '')[-cfg['need_characters']:]
                  +' '+previous_text[-cfg['previous_characters']:]
                  +' '+json.dumps([row['event']['content'] for row in projection['plan']], ensure_ascii=False))
    query = grams(query_text)
    selected = set(params.get('character_ids', [])) | set(participant_ids)
    profiles = projection['role_profile']
    profile_definition = settings()['categories']['role_profile']
    protagonist = next((row['event']['content'] for row in reversed(projection['story_setting'])
                        if row['event']['type_name'] == 'protagonist'), {})
    primary = {identity(row, profile_definition) for row in profiles if row['event']['content'].get('is_protagonist')}
    if isinstance(protagonist, dict):
        explicit = protagonist.get('character_id', protagonist.get('id'))
        if explicit: primary.add(explicit)
        name = protagonist.get('name')
        if name:
            primary.update(identity(row, profile_definition) for row in profiles if row['event']['content'].get('name') == name)
    selected.update(primary or [settings()['profile']['default_player_id']])
    input_need = raw+' '+params.get('scene_need', '')
    for row in profiles:
        profile = row['event']['content']
        character = identity(row, profile_definition)
        name = get_path(profile, settings()['profile']['name_path'], '')
        if character in selected or character in input_need or (name and name in input_need):
            selected.add(character)
    pin_ids = list(dict.fromkeys(params.get('event_ids', [])))
    pinned = sources.referenced(ctx, pin_ids)
    from .visibility import rows as visible_rows
    if len(visible_rows(repository,pinned))!=len(pinned):
        from script.util.errors import ContractError
        raise ContractError('DRAFT_NOT_ADOPTED','Recover current drafts explicitly by author packet ID')
    memory_definition = settings()['categories']['role_memory']
    for row in pinned:
        if row['event']['event_action'] != 'summarize' and row['event']['event_type'] in memory_definition['event_types']:
            selected.add(identity(row, memory_definition))
    keep = []
    counts = {}
    diagnostics = {}
    for name, definition, prefix in (('role_profile', profile_definition, 'profile'),
                                     ('role_memory', memory_definition, 'memory')):
        candidates = []
        chosen = []
        character_counts = {}
        for character in sorted(selected):
            records = [row for row in projection[name] if identity(row, definition) == character]
            recent, related = recent_related(records, query, cfg[prefix+'_recent'], cfg[prefix+'_related'])
            candidates.extend(records)
            chosen.extend(recent+related)
            character_counts[character] = {'total': len(records), 'selected': len(recent)+len(related),
                                           'recent': len(recent), 'related': len(related)}
            if name == 'role_memory':
                counts[character] = {'total': len(records), 'selected': len(recent)+len(related)}
        keep.extend(chosen)
        diagnostics[name] = selection_summary(projection[name], candidates, chosen,
            'recent_and_related_by_character',
            limits={'recent': cfg[prefix+'_recent'], 'related': cfg[prefix+'_related']},
            character_counts=character_counts)
    for name in ('world_fact', 'thread', 'historical_trace'):
        candidates = projection[name]
        candidate_scores = {row['event']['event_id']: score(row, query) for row in candidates}
        chosen = ranked(candidates, query, cfg[name+'_limit'], candidate_scores)
        keep.extend(chosen)
        diagnostics[name] = selection_summary(candidates, candidates, chosen, 'text_rank',
            limits={'total': cfg[name+'_limit']},
            scores=candidate_scores)
    relationships = [row for row in projection['relationship']
                     if any(character in json.dumps(row['event']['content'], ensure_ascii=False)
                            or character in row['object_id'] for character in selected)]
    # Projection is in narrative path order. Limit here, after replace/cancel, not in storage SQL.
    recent_relationships = relationships[-cfg['relationship_limit']:] if cfg['relationship_limit'] else []
    keep.extend(recent_relationships)
    diagnostics['relationship'] = selection_summary(projection['relationship'], relationships,
        recent_relationships, 'recent_matching_characters', limits={'total': cfg['relationship_limit']})
    for name in ('story_setting', 'plan', 'truth', 'secret', 'author_notes'):
        keep.extend(projection[name])
        diagnostics[name] = selection_summary(projection[name], projection[name], projection[name], 'all')
    diagnostics['user_input'] = selection_summary(projection['user_input'], [], [], 'explicit_only')
    automatic_count = len({row['event']['event_id'] for row in keep})
    keep.extend(pinned)
    expanded_ids = list(dict.fromkeys(event_id for row in keep for event_id in row.get('source_event_ids', [row['event']['event_id']])))
    # Forward original source events, not reducer-generated prose masquerading as old records.
    selected_sources = sources.referenced(ctx, expanded_ids)
    capsule_objects = set(params.get('object_ids', [])) | {row['object_id'] for row in keep}
    for name, definition in (('role_memory', memory_definition), ('role_profile', profile_definition)):
        capsule_objects.update(row['object_id'] for row in projection[name] if identity(row, definition) in selected)
    capsules = []
    if settings()['capsule_mode']:
        from .capsule.state import groups, project as capsule_project, policy
        by_object = groups(rows)
        objects = repository.records('object', {'object_id': list(capsule_objects)}) if capsule_objects else []
        capsule_objects = {obj['object_id'] for obj in objects if policy(obj['object_type'])['enabled']}
        for object_id in sorted(capsule_objects):
            capsules.extend(capsule_project(by_object.get(object_id, []))['overview'])
    else:
        capsule_objects = set()
    selected_projection = project(keep)
    selection_diagnostics = complete_diagnostics(diagnostics, selected_projection, pinned,
        history_source_count=len(rows), effective_event_count=sum(len(value) for value in projection.values()),
        automatic_event_count=automatic_count, source_count=len(selected_sources),
        explicit_source_count=len(pinned), query_characters=len(query_text), query_gram_count=len(query),
        capsule_count=len(capsules))
    result = {'view':params.get('view','compact'), 'scope': ctx, 'previous_scene_prose': previous_text, 'previous_summary': summary,
            'selected_character_ids': sorted(selected), 'sources': selected_sources,
            'projection': selected_projection, 'memory_counts': counts, 'selection_diagnostics': selection_diagnostics,
            'capsule_mode': settings()['capsule_mode'],
            'capsules': capsules, 'capsule_object_ids': sorted(capsule_objects)}
    if result['view']=='compact':result.pop('sources')
    return result


def lookup(repository, params):
    enabled()
    if params.get('maintenance_job_id'):
        from .maintenance import read_context
        return read_context(repository,params)
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    if params.get('view', 'full') == 'prose':
        from .prose import read_page
        return read_page(repository, ctx, params)
    source = scoped_sources(repository)
    if params.get('event_ids'):
        rows = source.referenced(ctx, params['event_ids'])
    else:
        rows = source.sources(ctx['history_node_id'], ctx['node_id'], object_ids=params.get('object_ids'),
                              event_types=params.get('event_types'), seq_max=ctx['history_event_seq'])
    from .visibility import rows as visible_rows
    selected_rows=visible_rows(repository,rows)
    if params.get('event_ids') and len(selected_rows)!=len(rows):
        from script.util.errors import ContractError
        raise ContractError('DRAFT_NOT_ADOPTED','Recover unpublished manuscripts through author-read with their packet ID')
    rows=selected_rows
    keyword = params.get('keyword', '').casefold()
    node_ids = params.get('source_node_ids')
    narratives = []
    if node_ids is not None:
        from .visibility import require_adopted
        require_adopted(repository,params['source_node_ids'])
        allowed = set(repository.ancestor_path(ctx['history_node_id'])) | {ctx['node_id']}
        if not set(node_ids) <= allowed:
            from script.util.errors import ContractError
            raise ContractError('SOURCE_NOT_VISIBLE', 'Requested prose is outside the creative path')
        rows = [row for row in rows if row['node_id'] in node_ids]
        for node_id in node_ids:
            node = repository.require('node', node_id)
            if node_id != ctx['node_id']:
                # Resolve only records captured before the scene's fixed history boundary.
                if node_id == ctx['history_node_id']:
                    node={**node,'narrative_event_id':ctx.get('previous_narrative_event_id',node['narrative_event_id'])}
                prose=read(repository,node,seq_max=ctx['history_event_seq'])
            else:
                prose = read(repository,node)
            narratives.append({'node_id':node_id,'narrative_event_id':node['narrative_event_id'],'literary_text':prose})
    if keyword:
        rows = [row for row in rows if keyword in searchable(row).casefold()]
    offset = params.get('offset', 0)
    limit = params.get('limit', settings()['recall']['lookup_limit'])
    page = rows[offset:offset+limit]
    return {'scope': ctx, 'view': 'full', 'sources': page, 'total': len(rows),
            'next_offset': offset+limit if offset+limit < len(rows) else None, 'narratives': narratives}
