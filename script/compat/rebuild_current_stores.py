"""Rebuild current development stores from the current data schema, preserving existing values.

SQLite tables are rebuilt in one transaction in the same database file, avoiding
Windows file replacement when an idle database console remains open.
"""
from pathlib import Path
import argparse
import json
import sqlite3
import sys
import tempfile
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from script.cli.bootstrap import bootstrap
bootstrap()
from script.util.contracts import DATA
from script.data.backends.sqlite import SQLiteStore
from script.data.config import load

ENTITIES=('node','object','event','relation')

def rebuild_sqlite(config):
    with tempfile.TemporaryDirectory(prefix='openstory-schema-ddl-') as tmp:
        template=SQLiteStore({**config,'location':str(Path(tmp)/'template.sqlite3')})
        try:
            template.initialize()
            tables={r['name']:r['sql'] for r in template.db.execute("SELECT name,sql FROM sqlite_schema WHERE type='table' AND name IN ('node','object','event','relation')")}
            indexes=[r['sql'] for r in template.db.execute("SELECT sql FROM sqlite_schema WHERE type='index' AND sql IS NOT NULL")]
        finally:template.close()
    db=sqlite3.connect(config['location'],isolation_level=None,timeout=5)
    try:
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('BEGIN IMMEDIATE')
        try:
            watermarks=dict(db.execute('SELECT name,seq FROM sqlite_sequence'))
            for entity in ENTITIES:
                temporary='__rebuild_'+entity
                ddl=tables[entity].replace('CREATE TABLE "'+entity+'"','CREATE TABLE "'+temporary+'"',1)
                db.execute(ddl)
                columns=','.join('"'+k+'"' for k in DATA['definitions'][entity]['properties'])
                existing={row[1] for row in db.execute('PRAGMA table_info("'+entity+'")')}
                expressions=[]
                for field in DATA['definitions'][entity]['properties']:
                    if field in existing:expressions.append('"'+field+'"')
                    elif entity=='event' and field=='event_action':expressions.append("'append'")
                    else:raise ValueError('Unsupported missing field: '+entity+'.'+field)
                db.execute('INSERT INTO "'+temporary+'" ('+columns+') SELECT '+','.join(expressions)+' FROM "'+entity+'"')
            for entity in ENTITIES:db.execute('DROP TABLE "'+entity+'"')
            for entity in ENTITIES:
                db.execute('ALTER TABLE "__rebuild_'+entity+'" RENAME TO "'+entity+'"')
                if entity in watermarks:
                    db.execute('UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name=?',(watermarks[entity],entity))
            for statement in indexes:db.execute(statement)
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK');raise
        finally:db.execute('PRAGMA foreign_keys=ON')
    finally:db.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',required=True)
    repo=Path(parser.parse_args().repo).resolve()
    result=[]
    for story in ('optional-local-sample','manual-playground'):
        for backend in ('sqlite',):
            config=load(repo/'story-data/debug'/story/(backend+'.json'))
            Path(config['location']).resolve().relative_to(repo/'story-data/debug')
            rebuild_sqlite(config)
            result.append({'database':config['database_id'],'backend':backend,'status':'updated'})
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
