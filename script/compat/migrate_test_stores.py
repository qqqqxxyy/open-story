"""One-shot conversion of the four authorized legacy v6 test stores.

This helper imports data; it does not run before/after consistency comparisons.
Legacy source cleanup happens only after selected destination transactions commit.
"""
from pathlib import Path
import argparse
import json
import shutil
import sqlite3
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from script.cli.bootstrap import bootstrap
bootstrap()
from script.data.api import connect

def load(path,backend):
    if backend=='file':
        raw=json.loads((path/'store.json').read_text(encoding='utf8'))
        return {k:list(raw[k].values()) for k in ('node','object','event','relation')}
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        raw={k:[dict(r) for r in db.execute('SELECT * FROM "'+k+'" ORDER BY seq')] for k in ('node','object','event','relation')}
    finally:db.close()
    for row in raw['event']:
        for k in ('content','res_1','res_2','res_3','res_4','res_5'):row[k]=json.loads(row[k])
    return raw

def clean_record(value):
    return {k:v for k,v in value.items() if k not in ('seq','created_time','modified_time','res_1','res_2','res_3','res_4','res_5')}

def convert(source,backend,destination_config):
    raw=load(source,backend);pointers={n['node_id']:{'predecessor_node_id':None,'narrative_event_id':None,'summary_event_id':None} for n in raw['node']}
    relations=[]
    for r in sorted(raw['relation'],key=lambda r:r['seq']):
        if r['kind']=='ownership':
            relations.append({'relation_id':r['relation_id'],'relation_type':'event','key_type':'event','key_id':r['event_id'],
                              'target_node_id':r['node_id'],'target_object_id':r['object_id'],'state':'active'})
        elif r['relation_type'] in ('node_predecessor','node_narrative','node_summary'):
            if r['state']=='active':
                field={'node_predecessor':'predecessor_node_id','node_narrative':'narrative_event_id','node_summary':'summary_event_id'}[r['relation_type']]
                pointers[r['source_id']][field]=r['target_id']
        else:
            relations.append({'relation_id':r['relation_id'],'relation_type':r['relation_type'],'key_type':r['source_kind'],
                              'key_id':r['source_id'],'target_'+r['target_kind']+'_id':r['target_id'],'state':r['state']})
    store=connect(destination_config)
    try:
        if store.query('node',limit=1)['total']:raise ValueError('Destination must be empty: '+str(destination_config))
        with store.transaction():
            for row in raw['node']:
                store.create('node',{'node_id':row['node_id'],'node_type':row['node_type'],'state':'creating'})
            for entity in ('object','event'):
                for row in raw[entity]:store.create(entity,clean_record(row))
            for row in relations:store.create('relation',row)
            # Predecessor is structural identity: populated only by this isolated conversion helper.
            for row in raw['node']:
                node=store.require('node',row['node_id'])
                value={**node,**pointers[row['node_id']],'state':row['state']}
                from script.util.contracts import validate
                validate(value,'node');store._check_node(value)
                store._replace('node',value)
        return {'database':store.config['database_id'],'backend':backend,'destination':store.config['location'],'status':'migrated'}
    finally:store.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',required=True);parser.add_argument('--cleanup-only',action='store_true')
    args=parser.parse_args();repo=Path(args.repo).resolve();old=(repo/'debug/data/runtime').resolve()
    old.relative_to(repo)
    items=[]
    for name in ('optional-local-sample',):
        for backend in ('sqlite',):
            source=old/(name+'.sqlite3' if backend=='sqlite' else name+'-file')
            source.resolve().relative_to(old)
            items.append((source,backend,repo/'story-data/debug'/name/(backend+'.json')))
    if args.cleanup_only:
        for _,backend,config in items:
            destination=config.parent/('story.sqlite3' if backend=='sqlite' else 'file/store.json')
            if not destination.exists():raise ValueError('Missing migrated destination: '+str(destination))
        results=[{'status':'already_migrated','config':str(config)} for _,_,config in items]
    else:
        results=[convert(*item) for item in items]
    print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
    for source,backend,_ in items:
        # Checked absolute source paths are confined to the explicitly authorized old test runtime.
        source.resolve().relative_to(old)
        if not source.exists():continue
        if backend=='file':shutil.rmtree(source)
        else:source.unlink()
    print('Old test stores removed')
if __name__=='__main__':main()
