"""Four business tables. JSON payloads are serialized, never interpreted here."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
from ..base import DataStore
from ..contracts import DATA,IDS,DataError,check_filters,page,validate

from script.util.versioning import current_version, validate_version

JSON_FIELDS={'content'}


class SQLiteStore(DataStore):
    def __init__(self,config):
        super().__init__(config)
        path=Path(config['location']);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=config.get('busy_timeout_ms',5000)/1000,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout='+str(config.get('busy_timeout_ms',5000)))

    def initialize(self):
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        if version != 0:validate_version(version)
        # application_id identifies an OpenStory data database, not another format version.
        application=self.db.execute('PRAGMA application_id').fetchone()[0]
        if application not in (0,0x4F535436):raise DataError('STORE_MISMATCH','Not an OpenStory database')
        if version==0 and self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
            raise DataError('STORE_MISMATCH','Do not initialize over an unrelated database')
        if version != 0:
            expected={entity:set(DATA['definitions'][entity]['properties']) for entity in IDS}
            actual={entity:{row['name'] for row in self.db.execute('PRAGMA table_info("'+entity+'")')} for entity in IDS}
            if actual!=expected:raise DataError('STORE_MISMATCH','Storage shape differs; use the isolated migration helper')
            return
        self.db.execute('BEGIN IMMEDIATE')
        try:
            nullable={'node':{'predecessor_node_id','narrative_event_id','summary_event_id'},
                      'relation':{'target_node_id','target_event_id','target_object_id'}}
            for entity in IDS:
                columns=[]
                for field in DATA['definitions'][entity]['properties']:
                    if field=='seq':columns.append('seq INTEGER PRIMARY KEY AUTOINCREMENT');continue
                    declaration='"'+field+'" TEXT'
                    if field==IDS[entity]:declaration+=' NOT NULL UNIQUE'
                    elif field not in nullable.get(entity,set()):declaration+=' NOT NULL'
                    if entity=='event' and field=='event_action':
                        values=DATA['definitions']['event']['properties']['event_action']['enum']
                        declaration+=" DEFAULT 'append' CHECK(event_action IN ("+','.join("'"+value+"'" for value in values)+'))'
                    columns.append(declaration)
                if entity=='node':
                    columns += ['FOREIGN KEY(predecessor_node_id) REFERENCES node(node_id)',
                                'FOREIGN KEY(narrative_event_id) REFERENCES event(event_id)',
                                'FOREIGN KEY(summary_event_id) REFERENCES event(event_id)',
                                "CHECK(node_type!='root' OR predecessor_node_id IS NULL)",
                                "CHECK(node_type!='scene' OR state!='active' OR (predecessor_node_id IS NOT NULL AND narrative_event_id IS NOT NULL AND summary_event_id IS NOT NULL))"]
                if entity=='relation':
                    columns += ['FOREIGN KEY(target_node_id) REFERENCES node(node_id)',
                                'FOREIGN KEY(target_event_id) REFERENCES event(event_id)',
                                'FOREIGN KEY(target_object_id) REFERENCES object(object_id)',
                                "CHECK(target_node_id IS NOT NULL OR target_event_id IS NOT NULL OR target_object_id IS NOT NULL)",
                                "CHECK(relation_type!='event' OR (key_type='event' AND target_node_id IS NOT NULL AND target_object_id IS NOT NULL AND target_event_id IS NULL AND state='active'))"]
                self.db.execute('CREATE TABLE IF NOT EXISTS "'+entity+'" ('+','.join(columns)+') STRICT')
            for statement in [
                "CREATE UNIQUE INDEX IF NOT EXISTS event_owner_unique ON relation(key_id) WHERE relation_type='event' AND key_type='event'",
                'CREATE INDEX IF NOT EXISTS relation_key ON relation(key_type,key_id,relation_type,state)',
                'CREATE INDEX IF NOT EXISTS relation_target_node ON relation(target_node_id,relation_type,key_id)',
                'CREATE INDEX IF NOT EXISTS relation_target_event ON relation(target_event_id,relation_type,key_id)',
                'CREATE INDEX IF NOT EXISTS relation_target_object ON relation(target_object_id,relation_type,key_id)',
                'CREATE INDEX IF NOT EXISTS node_predecessor ON node(predecessor_node_id)',
                "CREATE UNIQUE INDEX IF NOT EXISTS branch_head_branch ON relation(key_id) WHERE relation_type='branch_head'",
                "CREATE UNIQUE INDEX IF NOT EXISTS branch_head_node ON relation(target_node_id) WHERE relation_type='branch_head'",
                "CREATE INDEX IF NOT EXISTS event_scope_object ON relation(target_object_id,target_node_id,key_id) WHERE relation_type='event' AND key_type='event'",
                'CREATE INDEX IF NOT EXISTS node_narrative ON node(narrative_event_id)',
                'CREATE INDEX IF NOT EXISTS node_summary ON node(summary_event_id)',
                'CREATE INDEX IF NOT EXISTS event_category ON event(event_type,state,seq)',
                'CREATE INDEX IF NOT EXISTS object_category ON object(object_type,object_key)',
                'CREATE INDEX IF NOT EXISTS node_state ON node(state,seq)']:
                self.db.execute(statement)
            self.db.execute('PRAGMA user_version='+str(current_version()));self.db.execute('PRAGMA application_id=1330861110')
            self.db.execute('COMMIT')
        except Exception as exc:
            self.db.execute('ROLLBACK')
            if isinstance(exc,sqlite3.Error):raise DataError('STORAGE_ERROR',str(exc)) from exc
            raise

    @property
    def skill_version(self):
        return self.db.execute('PRAGMA user_version').fetchone()[0]

    @contextmanager
    def transaction(self):
        if self._depth:
            self._depth+=1
            try:yield self
            finally:self._depth-=1
            return
        self.db.execute('BEGIN IMMEDIATE');self._depth=1;self._affected_events=set()
        changes_before=self.db.total_changes
        try:
            yield self
            self._validate_ownership()
            if self.db.total_changes != changes_before:
                self.db.execute('PRAGMA user_version='+str(current_version()))
            self.db.execute('COMMIT')
        except Exception as exc:
            self.db.execute('ROLLBACK')
            if isinstance(exc,sqlite3.Error):raise DataError('STORAGE_ERROR',str(exc)) from exc
            raise
        finally:self._depth=0;self._affected_events=set()

    def _decode(self,entity,row):
        if row is None:return None
        value=dict(row)
        for field in JSON_FIELDS & set(value):value[field]=json.loads(value[field])
        validate(value,entity)
        return value
    def get(self,entity,record_id):
        return self._decode(entity,self.db.execute('SELECT * FROM "'+entity+'" WHERE '+IDS[entity]+'=?',(record_id,)).fetchone())

    def _where(self,entity,filters,prefix=''):
        check_filters(entity,filters)
        parts=[];args=[]
        for key,value in filters.items():
            column=prefix+'"'+key+'"'
            if isinstance(value,list):
                if not value:parts.append('0');continue
                parts.append(column+' IN ('+','.join('?' for _ in value)+')');args.extend(value)
            elif value is None:parts.append(column+' IS NULL')
            else:parts.append(column+'=?');args.append(value)
        return parts,args

    def query(self,entity,filters=None,limit=100,offset=0,descending=False):
        parts,args=self._where(entity,filters or {})
        where=' WHERE '+' AND '.join(parts) if parts else ''
        total=self.db.execute('SELECT COUNT(*) FROM "'+entity+'"'+where,args).fetchone()[0]
        rows=self.db.execute('SELECT * FROM "'+entity+'"'+where+' ORDER BY seq '+('DESC' if descending else 'ASC')+' LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
        return page([self._decode(entity,row) for row in rows],total,offset,limit)

    def events_for(self,owner_kind,owner_id,filters=None,node_ids=None,limit=100,offset=0,descending=False):
        if owner_kind not in ('node','object'):raise DataError('INVALID_OWNER','node or object required')
        parts,args=self._where('event',filters or {},'e.')
        parts.extend(["r.relation_type='event' AND r.key_type='event'",'r.target_'+owner_kind+'_id=?']);args.append(owner_id)
        if node_ids is not None:
            parts.append('r.target_node_id IN ('+','.join('?' for _ in node_ids)+')' if node_ids else '0');args.extend(node_ids)
        joined=' FROM event e JOIN relation r ON e.event_id=r.key_id WHERE '+' AND '.join(parts)
        total=self.db.execute('SELECT COUNT(*)'+joined,args).fetchone()[0]
        rows=self.db.execute('SELECT e.*'+joined+' ORDER BY e.seq '+('DESC' if descending else 'ASC')+' LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
        return page([self._decode('event',row) for row in rows],total,offset,limit)

    def _columns(self,entity,fields=None,prefix=''):
        known=DATA['definitions'][entity]['properties']
        if fields is not None and (not fields or set(fields)-set(known)):
            raise DataError('INVALID_FIELDS','Use documented record fields')
        selected=list(known) if fields is None else [f for f in known if f in fields]
        return ','.join(prefix+'"'+f+'"' for f in selected)

    def _projection(self,entity,row,fields):
        if fields is None:return self._decode(entity,row)
        result=dict(row)
        for field in JSON_FIELDS & set(result):result[field]=json.loads(result[field])
        return result

    def records(self,entity,filters=None,fields=None,limit=None):
        parts,args=self._where(entity,filters or {})
        where=' WHERE '+' AND '.join(parts) if parts else ''
        statement='SELECT '+self._columns(entity,fields)+' FROM "'+entity+'"'+where+' ORDER BY seq'
        if limit is not None:statement+=' LIMIT ?';args.append(limit)
        return [self._projection(entity,row,fields) for row in self.db.execute(statement,args)]

    def exists(self,entity,filters):
        parts,args=self._where(entity,filters)
        where=' WHERE '+' AND '.join(parts) if parts else ''
        return self.db.execute('SELECT 1 FROM "'+entity+'"'+where+' LIMIT 1',args).fetchone() is not None

    @staticmethod
    def _path_cte():
        return ("WITH RECURSIVE path(node_id,predecessor_node_id,depth) AS ("
                "SELECT node_id,predecessor_node_id,0 FROM node WHERE node_id=? UNION ALL "
                "SELECT n.node_id,n.predecessor_node_id,p.depth+1 FROM node n JOIN path p ON n.node_id=p.predecessor_node_id) ")

    def ancestor_path(self,end_node_id):
        return [r[0] for r in self.db.execute(self._path_cte()+'SELECT node_id FROM path ORDER BY depth DESC',(end_node_id,))]

    def is_ancestor(self,end_node_id,node_id):
        return self.db.execute(self._path_cte()+'SELECT 1 FROM path WHERE node_id=? LIMIT 1',(end_node_id,node_id)).fetchone() is not None

    def events_on_path(self,end_node_id,object_ids=None,filters=None,fields=None,
                       limit=100,offset=0,descending=False,include_total=True):
        validate({'end_node_id':end_node_id,'object_ids':object_ids,'filters':filters or {},'fields':fields,'limit':limit,'offset':offset,'descending':descending,'include_total':include_total},'path_event_query')
        parts,args=self._where('event',filters or {},'e.')
        parts += ["r.relation_type='event'", "r.key_type='event'", 'r.target_node_id IN (SELECT node_id FROM path)']
        if object_ids is not None:
            parts.append('r.target_object_id IN ('+','.join('?' for _ in object_ids)+')' if object_ids else '0')
            args.extend(object_ids)
        joined=' FROM relation r JOIN event e ON e.event_id=r.key_id WHERE '+' AND '.join(parts)
        parameters=[end_node_id,*args]
        total=self.db.execute(self._path_cte()+'SELECT COUNT(*)'+joined,parameters).fetchone()[0] if include_total else None
        fetch_limit=limit if include_total else limit+1
        rows=self.db.execute(self._path_cte()+'SELECT '+self._columns('event',fields,'e.')+joined+
            ' ORDER BY e.seq '+('DESC' if descending else 'ASC')+' LIMIT ? OFFSET ?',[*parameters,fetch_limit,offset]).fetchall()
        more=(offset+len(rows)<total) if include_total else len(rows)>limit
        return {'items':[self._projection('event',row,fields) for row in rows[:limit]],'total':total,
                'offset':offset,'next_offset':offset+limit if more else None}

    @staticmethod
    def _in(column,values,args):
        if not values:return '0'
        args.extend(values)
        return column+' IN ('+','.join('?' for _ in values)+')'



    def max_sequence(self,entity):
        if entity not in IDS:raise DataError('INVALID_ENTITY',entity)
        return self.db.execute('SELECT COALESCE(MAX(seq),0) FROM "'+entity+'"').fetchone()[0]

    def source_records(self,end_node_id,current_node_id=None,event_ids=None,object_ids=None,event_types=None,seq_max=None,all_nodes=False):
        validate({'end_node_id':end_node_id,'current_node_id':current_node_id,'event_ids':event_ids,'object_ids':object_ids,'event_types':event_types,'seq_max':seq_max,'all_nodes':all_nodes},'source_query')
        # One JOIN includes ownership and path order; no per-event ownership calls.
        parts=["r.relation_type='event'", "r.key_type='event'"]
        args=[]
        if not all_nodes:
            scope='r.target_node_id IN (SELECT node_id FROM path)'
            if seq_max is not None:
                scope='('+scope+' AND e.seq<=?)';args.append(seq_max)
            if current_node_id is not None:
                scope='('+scope+' OR r.target_node_id=?)';args.append(current_node_id)
            parts.append(scope)
        for column,values in [('e.event_id',event_ids),('r.target_object_id',object_ids),('e.event_type',event_types)]:
            if values is not None:parts.append(self._in(column,values,args))
        prefix='' if all_nodes else self._path_cte()
        parameters=args if all_nodes else [end_node_id,*args]
        order='n.seq,e.seq' if all_nodes else 'COALESCE((SELECT depth FROM path WHERE node_id=n.node_id),-1) DESC,e.seq'
        query=prefix+'SELECT e.*,r.target_node_id AS owner_node,r.target_object_id AS owner_object FROM relation r JOIN event e ON e.event_id=r.key_id JOIN node n ON n.node_id=r.target_node_id WHERE '+' AND '.join(parts)+' ORDER BY '+order
        result=[]
        for row in self.db.execute(query,parameters):
            value=dict(row);node=value.pop('owner_node');obj=value.pop('owner_object')
            result.append({'event':self._decode('event',value),'node_id':node,'object_id':obj})
        return result

    def descendants(self,node_id,include_anchor=True):
        self.require('node',node_id)
        query=("WITH RECURSIVE descendants(node_id,depth) AS (SELECT node_id,0 FROM node WHERE node_id=? "
               "UNION ALL SELECT n.node_id,d.depth+1 FROM node n JOIN descendants d ON n.predecessor_node_id=d.node_id) "
               "SELECT n.*,d.depth AS descendant_depth FROM node n JOIN descendants d ON n.node_id=d.node_id "
               +("" if include_anchor else "WHERE d.depth>0 ")+"ORDER BY d.depth DESC,n.seq DESC")
        result=[]
        for row in self.db.execute(query,[node_id]):
            value=dict(row);depth=value.pop('descendant_depth')
            result.append({'node':self._decode('node',value),'depth':depth})
        validate(result,'descendants')
        return result

    def references(self,node_ids=(),event_ids=(),object_ids=()):
        terms=[];args=[]
        for kind,ids in (('node',node_ids),('event',event_ids),('object',object_ids)):
            if ids:
                terms.append("(key_type='"+kind+"' AND "+self._in('key_id',ids,args)+')')
                terms.append(self._in('target_'+kind+'_id',ids,args))
        relations=[self._decode('relation',row) for row in self.db.execute('SELECT * FROM relation WHERE '+' OR '.join(terms),args)] if terms else []
        terms=[];args=[]
        if node_ids:terms.append(self._in('predecessor_node_id',node_ids,args))
        if event_ids:
            terms.append(self._in('narrative_event_id',event_ids,args));terms.append(self._in('summary_event_id',event_ids,args))
        nodes=[dict(row) for row in self.db.execute('SELECT node_id,predecessor_node_id,narrative_event_id,summary_event_id FROM node WHERE '+' OR '.join(terms),args)] if terms else []
        return {'relations':relations,'nodes':nodes}

    def delete_many(self,entity,record_ids):
        ids=list(dict.fromkeys(record_ids))
        if not ids:return 0
        with self.transaction():
            if entity=='relation':
                owners=self.records('relation',{'relation_id':ids,'relation_type':'event'},fields=['key_id'])
                self._affected_events.update(r['key_id'] for r in owners)
            else:
                refs=self.references(**{entity+'_ids':ids})
                outside_nodes=[r for r in refs['nodes'] if entity!='node' or r['node_id'] not in ids]
                if refs['relations'] or outside_nodes:raise DataError('REFERENCED','Remove references first')
                if entity=='event':self._affected_events.update(ids)
            args=[];where=self._in(IDS[entity],ids,args)
            cursor=self.db.execute('DELETE FROM "'+entity+'" WHERE '+where,args)
            if cursor.rowcount!=len(ids):raise DataError('NOT_FOUND','Some deletion records do not exist')
            return cursor.rowcount

    def _validate_ownership(self):
        if not self._affected_events:return
        args=[];where=self._in('e.event_id',list(self._affected_events),args)
        invalid=self.db.execute("SELECT e.event_id FROM event e LEFT JOIN relation r ON r.key_id=e.event_id "
            "AND r.relation_type='event' AND r.key_type='event' WHERE "+where+
            ' GROUP BY e.event_id HAVING COUNT(r.relation_id)!=1 LIMIT 1',args).fetchone()
        if invalid:raise DataError('MISSING_OWNERSHIP','An event must have exactly one ownership')

    def _encoded(self,value):return {k:json.dumps(v,ensure_ascii=False,allow_nan=False) if k in JSON_FIELDS else v for k,v in value.items()}
    def _insert(self,entity,value):
        encoded=self._encoded(value);fields=list(encoded)
        self.db.execute('INSERT INTO "'+entity+'" ('+','.join('"'+f+'"' for f in fields)+') VALUES ('+','.join('?' for _ in fields)+')',list(encoded.values()))
        return self.get(entity,value[IDS[entity]])
    def _replace(self,entity,value):
        encoded=self._encoded(value);fields=[k for k in encoded if k not in ('seq',IDS[entity])]
        self.db.execute('UPDATE "'+entity+'" SET '+','.join('"'+k+'"=?' for k in fields)+' WHERE '+IDS[entity]+'=?',[*[encoded[k] for k in fields],value[IDS[entity]]])
    def _remove(self,entity,record_id):self.db.execute('DELETE FROM "'+entity+'" WHERE '+IDS[entity]+'=?',(record_id,))
    def close(self):self.db.close()
