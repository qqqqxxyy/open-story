"""Convert current SQLite samples to leaf-only current head relationships."""
from pathlib import Path
import argparse,json,sqlite3,sys
from datetime import datetime,timezone
from uuid import uuid4
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from script.cli.bootstrap import bootstrap
bootstrap()
from script.data.config import load

INDEXES=[
    "CREATE UNIQUE INDEX IF NOT EXISTS branch_head_branch ON relation(key_id) WHERE relation_type='branch_head'",
    "CREATE UNIQUE INDEX IF NOT EXISTS branch_head_node ON relation(target_node_id) WHERE relation_type='branch_head'",
    "CREATE INDEX IF NOT EXISTS event_scope_object ON relation(target_object_id,target_node_id,key_id) WHERE relation_type='event' AND key_type='event'"
]

def upgrade(config):
    db=sqlite3.connect(config['location'],isolation_level=None);db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        try:
            leaves=[r['node_id'] for r in db.execute('SELECT n.node_id FROM node n WHERE NOT EXISTS(SELECT 1 FROM node c WHERE c.predecessor_node_id=n.node_id) ORDER BY n.seq')]
            old_heads=[dict(r) for r in db.execute("SELECT * FROM relation WHERE relation_type='branch_head' AND state='active' ORDER BY seq DESC")]
            old_tags={r['key_id']:r['target_object_id'] for r in db.execute("SELECT * FROM relation WHERE relation_type='node_branch'")}
            db.execute("DELETE FROM relation WHERE relation_type IN ('node_branch','branch_head')")
            used=set();now=datetime.now(timezone.utc).isoformat()
            for leaf in leaves:
                chosen=next((r for r in old_heads if r['target_node_id']==leaf and r['key_id'] not in used),None)
                branch_id=chosen['key_id'] if chosen else old_tags.get(leaf,'branch-'+leaf)
                if branch_id in used:branch_id='branch-'+leaf
                used.add(branch_id)
                if not db.execute('SELECT 1 FROM object WHERE object_id=?',(branch_id,)).fetchone():
                    db.execute('INSERT INTO object(object_id,object_type,object_key,name,created_time,modified_time) VALUES(?,?,?,?,?,?)',(branch_id,'branch',branch_id,branch_id,now,now))
                row=chosen or {'relation_id':'rel-'+uuid4().hex,'relation_type':'branch_head','key_type':'object','key_id':branch_id,'state':'active',
                    'target_node_id':leaf,'target_event_id':None,'target_object_id':None,'created_time':now,'modified_time':now}
                columns=list(row)
                db.execute('INSERT INTO relation('+','.join('"'+c+'"' for c in columns)+') VALUES('+','.join('?' for _ in columns)+')',list(row.values()))
            for statement in INDEXES:db.execute(statement)
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'database':config['database_id'],'leaf_heads':len(leaves),'status':'updated'}
    finally:db.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',required=True)
    repo=Path(parser.parse_args().repo).resolve();results=[]
    for story in ('optional-local-sample',):
        config=load(repo/'story-data/debug'/story/'sqlite.json')
        Path(config['location']).resolve().relative_to(repo/'story-data/debug')
        results.append(upgrade(config))
    print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
