"""Persist compact packets and expand their explicit context references once."""
from copy import deepcopy
from script.workflow.data.creative import CreativeRepository
from script.util.errors import ContractError
from .common import enabled, context, writable, append, identifier, latest, local, messages


def packet_refs(content):
    refs = list(content.get('context_event_ids', []))
    for name in ('planning_event_ids', 'truth_event_ids', 'raw_input_event_ids', 'capsule_event_ids'):
        refs.extend(content.get(name, []))
    if content.get('previous_narrative_event_id'):
        refs.append(content['previous_narrative_event_id'])
    for group in content.get('groups', []):
        refs.extend(group['event_ids'])
    return list(dict.fromkeys(refs))


def save_director(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    content = deepcopy(params['content'])
    if ctx.get('attempt_id'):content['attempt_id']=ctx['attempt_id']
    content['raw_input_event_ids'] = ctx['raw_input_event_ids']
    content['previous_narrative_event_id'] = ctx.get('previous_narrative_event_id')
    refs = packet_refs(content)
    sources = CreativeRepository(repository)
    referenced=sources.referenced(ctx, refs)
    from .visibility import rows as visible_rows
    if len(visible_rows(repository,referenced))!=len(referenced):
        raise ContractError('DRAFT_NOT_ADOPTED','Do not put unadopted prose in normal director sources')
    previous = latest(repository, ctx['node_id'], 'director_packet')
    if previous and previous['content'] == content:
        event = previous
    else:
        writable(repository, ctx)
        with repository.transaction():
            event = append(repository, ctx, 'director_packet', ctx['node_id'], content)
    return {'packet_event_id': event['event_id'], 'node_id': ctx['node_id'], 'source_count': len(refs)}


def read_director(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    event = repository.require('event', params['packet_event_id']) if params.get('packet_event_id') else latest(repository, ctx['node_id'], 'director_packet')
    if not event or event['event_type'] != 'director_packet' or repository.owner(event['event_id'])['node_id'] != ctx['node_id']:
        raise ContractError('PACKET_NOT_FOUND', 'Director packet is not part of this scene')
    content = event['content']
    rows = CreativeRepository(repository).referenced(ctx, packet_refs(content))
    inputs = set(content['raw_input_event_ids'])
    from .narrative import read
    previous = repository.require('node',ctx['history_node_id'])
    previous = {**previous,'narrative_event_id':content['previous_narrative_event_id']}
    prose = read(repository,previous) or ''
    skip = inputs | {content.get('previous_narrative_event_id')}
    return {'packet_event_id': event['event_id'], 'scope': ctx, 'brief': content,
            'sources': [row for row in rows if row['event']['event_id'] not in skip],
            'previous_scene_prose': prose,
            'raw_user_messages': [message for row in rows if row['event']['event_id'] in inputs for message in messages(row['event']['content'])],
            'author_policy': 'role-interaction/director-author/contract.md'}


def save_author(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    from . import manuscripts
    active=manuscripts.check_attempt(repository,ctx['node_id'],params.get('attempt_id'))
    if ctx['mode'] == 'dialogue' and (not active or active['kind']=='initial'):
        raise ContractError('USE_DIALOGUE_TURN', 'Use dialogue-turn-save and dialogue-close')
    content = params['content']
    narrative_id = identifier('narrative',ctx['node_id'],active['attempt_id']) if active else identifier('narrative',ctx['node_id'])
    packet_id = manuscripts.author_id(repository,ctx['node_id'])
    with repository.transaction():
        narrative = append(repository, ctx, 'narrative', ctx['node_id'], {'literary_text': content['literary_text']}, narrative_id, select_as='narrative')
        handoffs=[row['event'] for row in local(repository,ctx['node_id'],['director_packet'])]
        prior=latest(repository,ctx['node_id'],'author_packet')
        source_id=params.get('source_packet_event_id') or (prior['content']['director_packet_event_id'] if prior else None)
        if source_id is None and len(handoffs)>1:
            raise ContractError('PACKET_REFERENCE_REQUIRED','Specify the actual director packet used by the author')
        handoff=next((item for item in handoffs if item['event_id']==source_id),None) if source_id else (handoffs[0] if handoffs else None)
        if handoff is None:raise ContractError('PACKET_NOT_FOUND','Director packet is not owned by this scene')
        if active:
            if active['kind']=='minor':
                base=repository.require('event',active['base_author_packet_event_id'])
                valid=handoff['event_id']==base['content']['director_packet_event_id']
            else:valid=handoff['content'].get('attempt_id')==active['attempt_id']
            if not valid:raise ContractError('PACKET_REFERENCE_REQUIRED','Use the director packet belonging to this attempt or the minor revision base')
        value = {key: deepcopy(value) for key, value in content.items() if key != 'literary_text'}
        value.update(narrative_event_id=narrative['event_id'], director_packet_event_id=handoff['event_id'])
        if active:value['attempt_id']=active['attempt_id']
        event = append(repository, ctx, 'author_packet', ctx['node_id'], value, packet_id)
    return {'packet_event_id': event['event_id'], 'narrative_event_id': narrative_id, 'node_id': ctx['node_id'],
            'source_packet_event_id':handoff['event_id'],'source_is_latest':handoff['event_id']==handoffs[-1]['event_id']}


def read_author(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    from . import manuscripts
    if manuscripts.attempt(repository,ctx['node_id']) and not manuscripts.adoption(repository,ctx['node_id']) and not params.get('packet_event_id'):
        raise ContractError('DRAFT_NOT_ADOPTED','Recover the current draft explicitly by author packet ID')
    event = repository.require('event', params['packet_event_id']) if params.get('packet_event_id') else latest(repository, ctx['node_id'], 'author_packet')
    if not event or event['event_type'] != 'author_packet' or repository.owner(event['event_id'])['node_id'] != ctx['node_id']:
        raise ContractError('PACKET_NOT_FOUND', 'Author packet is not part of this scene')
    from .narrative import read
    node = {**repository.require('node', ctx['node_id']), 'narrative_event_id': event['content']['narrative_event_id']}
    return {'packet_event_id': event['event_id'], 'narrative_event_id': event['content']['narrative_event_id'],
            'literary_text': read(repository, node),
            'feedback': event['content'].get('feedback', {}), 'reply': event['content']}


def close_dialogue(repository, ctx, content):
    from . import manuscripts
    active=manuscripts.check_attempt(repository,ctx['node_id'])
    old = manuscripts.packet(repository,ctx['node_id'])
    if old:
        from .narrative import read
        node={**repository.require('node',ctx['node_id']),'narrative_event_id':old['content']['narrative_event_id']}
        changed='final_literary_text' in content and read(repository,node)!=content['final_literary_text']
        if 'feedback' in content and content['feedback']!=old['content'].get('feedback',{}):changed=True
        if content.get('closing_text'):
            closing=repository.get('event',identifier('closing',ctx['node_id']))
            changed=changed or not closing or closing['content']['literary_text']!=content['closing_text']
        if changed:raise ContractError('IDEMPOTENCY_CONFLICT','Closed dialogue retry must preserve the saved final text and feedback')
        return {'packet_event_id': old['event_id'], 'narrative_event_id': old['content']['narrative_event_id'], 'node_id': ctx['node_id']}
    writable(repository, ctx)
    rows = local(repository, ctx['node_id'], ['user_input', 'dialogue_fragment'])
    fragments = [row['event'] for row in rows if row['event']['event_type'] == 'dialogue_fragment']
    replied = {event['content']['turn_id'] for event in fragments}
    if not fragments or any(row['event']['event_id'] not in replied for row in rows if row['event']['event_type'] == 'user_input'):
        raise ContractError('TURN_PENDING', 'Complete every saved dialogue input before closing')
    with repository.transaction():
        ids = [event['event_id'] for event in fragments]
        if content.get('closing_text'):
            closing = append(repository, ctx, 'dialogue_fragment', ctx['node_id'], {'literary_text': content['closing_text'], 'turn_id': 'closing'}, identifier('closing', ctx['node_id']))
            ids.append(closing['event_id'])
        narrative_id = identifier('narrative',ctx['node_id'],active['attempt_id']) if active else identifier('narrative',ctx['node_id'])
        body={'literary_text':content['final_literary_text']} if content.get('final_literary_text') else {'fragment_event_ids':ids}
        append(repository,ctx,'narrative',ctx['node_id'],body,narrative_id,select_as='narrative')
        handoff=latest(repository,ctx['node_id'],'director_packet')
        value={'narrative_event_id':narrative_id,'feedback':content.get('feedback',{}),'director_packet_event_id':handoff['event_id'] if handoff else None}
        if active:value['attempt_id']=active['attempt_id']
        packet=append(repository,ctx,'author_packet',ctx['node_id'],value,manuscripts.author_id(repository,ctx['node_id']))
    return {'packet_event_id': packet['event_id'], 'narrative_event_id': narrative_id, 'node_id': ctx['node_id']}


def save_turn(repository, params):
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    if ctx['mode'] != 'dialogue':
        raise ContractError('USE_NORMAL_REPLY', 'This is not a dialogue scene')
    input_event = repository.require('event', params['turn_id'])
    if input_event['event_type'] != 'user_input' or repository.owner(input_event['event_id'])['node_id'] != ctx['node_id']:
        raise ContractError('TURN_NOT_FOUND', 'Turn input belongs to a different scene')
    event_id = identifier('fragment', ctx['node_id'], params['turn_id'])
    content = {**deepcopy(params['content']), 'turn_id': params['turn_id']}
    final_text=content.pop('final_literary_text',None)
    with repository.transaction():
        event = append(repository, ctx, 'dialogue_fragment', ctx['node_id'], content, event_id)
        result = {'node_id': ctx['node_id'], 'fragment_event_id': event['event_id'], 'scene_complete': content['scene_complete']}
        if content['scene_complete']:
            result.update(close_dialogue(repository,ctx,{'feedback':content.get('feedback',{}),**({'final_literary_text':final_text} if final_text is not None else {})}))
    return result


def read_dialogue(repository, params):
    """Read one submitted turn by receipt, or the full scene for recovery."""
    enabled()
    ctx = context(repository, params['node_id'], params.get('branch_id'))
    fragment_id = params.get('fragment_event_id')
    if fragment_id:
        fragment = repository.require('event', fragment_id)
        if fragment['event_type'] != 'dialogue_fragment' or repository.owner(fragment_id)['node_id'] != ctx['node_id']:
            raise ContractError('TURN_NOT_FOUND', 'Dialogue fragment is not part of this scene')
        turn_id = fragment['content']['turn_id']
        inputs = [] if turn_id == 'closing' else [repository.require('event', turn_id)]
        return {'scope': ctx, 'fragments': [fragment], 'inputs': inputs}
    return {'scope': ctx,
            'fragments': [row['event'] for row in local(repository, ctx['node_id'], ['dialogue_fragment'])],
            'inputs': [row['event'] for row in local(repository, ctx['node_id'], ['user_input'])]}
