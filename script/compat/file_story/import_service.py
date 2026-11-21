"""Transactional historical import through Repository; never direct SQL."""
from pathlib import Path
from copy import deepcopy
from .inventory import stable, load, digest, check_sources
from script.workflow.data.story_stores import StoryStores
from script.workflow.pipeline.creative.actions import register_targets


def install(plan, target_directory):
    folder=Path(target_directory).resolve()
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('Target must be empty; existing stories are never overwritten')
    check_sources(plan)
    # StoryStores only provisions configuration and storage; online is the eventual location.
    stores=StoryStores(folder.parent.parent)
    repo,location=stores.provision(folder.name,folder.parent.name)
    try:
        with repo.transaction():
            for n in plan['node_order']:
                meta=plan['nodes'][n]
                repo.create('node',{'node_id':n,'node_type':'root' if meta['kind']=='root' else 'scene',
                                   'predecessor_node_id':meta['creation_parent_id']})
            by_id={}
            for row in plan['events']:
                node=repo.require('node',row['node_id'])
                if node['state'] not in ('creating','updating'):raise ValueError('Import node must be writable')
                targets=row['target_event_ids']
                if targets and row['event']['event_action'] not in ('replace','cancel'):raise ValueError('Invalid control action')
                if row['event']['event_action'] in ('replace','cancel') and not targets:raise ValueError('Missing action target')
                allowed=set(repo.ancestor_path(row['node_id']))
                for target in targets:
                    old=by_id.get(target)
                    if not old or old['node_id'] not in allowed or old['object']['object_id']!=row['object']['object_id']:
                        raise ValueError('Action target must be earlier, visible and in the same object')
                    if old['event']['event_action'] not in ('append','replace'):raise ValueError('Target is not a content record')
                repo.ensure_object(row['object'])
                repo.append_event(row['node_id'],row['object']['object_id'],row['event'])
                register_targets(repo,row['event']['event_id'],targets)
                by_id[row['event']['event_id']]=row
            for n in plan['node_order']:
                if plan['nodes'][n]['kind']=='scene':
                    narrative=stable(plan['story_id'],'nodes/'+n+'/narrative.md','')
                    summary=stable(plan['story_id'],'nodes/'+n+'/delta.json','/scene')
                    if repo.owner(narrative)['node_id']!=n or repo.owner(summary)['node_id']!=n:raise ValueError('Nonlocal selection')
                    if not repo.require('event',narrative)['content']['literary_text']:raise ValueError('Empty scene prose')
                    repo.select(n,narrative,'narrative');repo.select(n,summary,'summary')
                repo.update('node',n,{'state':'active'})
            leaves={n for n in plan['node_order'] if not repo.has_successors(n)}
            heads={b['head_node_id'] for b in plan['branches']}
            if leaves!=heads or len(heads)!=len(plan['branches']):raise ValueError('Exactly one branch head per real leaf required')
            for branch in plan['branches']:
                key=branch['branch_id']
                repo.ensure_object({'object_id':key,'object_type':'branch','object_key':key,'name':branch['name']})
                repo.assign_head(key,branch['head_node_id'])
            result={**location,'counts':repo.info()['counts'],'story_id':plan['story_id'],
                    'default_branch_id':plan['default_branch_id'],'branches':[b['branch_id'] for b in plan['branches']]}
        return result
    finally:
        repo.close()
