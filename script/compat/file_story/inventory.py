"""Read-only legacy files, selected graph and provenance addresses."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
import json


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(value):
    return sha256(value).hexdigest()


def stable(story, file, pointer):
    return 'import-' + digest((story+'\0'+file+'\0'+pointer).encode('utf8'))[:32]


def check_sources(plan):
    """Verify declared main and supplemental sources before target provisioning."""
    source = Path(plan['source'])
    roots = {'primary': source}
    for file, expected in plan['source_hashes'].items():
        if digest((source/file).read_bytes()) != expected:
            raise ValueError('Source changed since planning: '+file)
    for key, descriptor in plan.get('supplemental_sources', {}).items():
        root = Path(descriptor['root'])
        roots[key] = root
        for file, expected in descriptor['hashes'].items():
            if digest((root/file).read_bytes()) != expected:
                raise ValueError('Supplemental source changed since planning: '+key+'/'+file)
    for row in plan['events']:
        content = row['event']['content']
        payload = content.get('payload') if isinstance(content, dict) else None
        provenance = content.get('provenance') if isinstance(content, dict) else None
        if not provenance and isinstance(payload, dict):
            provenance = payload.get('_migration_provenance')
        if provenance:
            root = roots[provenance.get('source_id', 'primary')]
            if digest((root/provenance['source_file']).read_bytes()) != provenance['source_sha256']:
                raise ValueError('Creative source changed since planning')


class Source:
    def __init__(self, root, branch_ids):
        self.root = Path(root).resolve()
        self.story = load(self.root/'story.json')
        if self.story['version'] != 4:
            raise ValueError('This adapter reads storage format 4 only')
        self.all_nodes = {p.parent.name: load(p) for p in (self.root/'nodes').glob('*/meta.json')}
        self.branches = [load(self.root/'graph/branches'/ (key+'.json')) for key in branch_ids]
        self.paths = {b['branch_id']: self.path(b['head_node_id']) for b in self.branches}
        retained = {n for path in self.paths.values() for n in path}
        self.nodes = {n: self.all_nodes[n] for n in retained}
        self.order = sorted(retained, key=lambda n: (len(self.path(n)), self.nodes[n]['created_at'], n))
        self.inputs = {n: load(self.root/'nodes'/n/'input.json') for n in self.order}
        self.deltas = {n: load(self.root/'nodes'/n/'delta.json') for n in self.order}
        self.prose = {n: (self.root/'nodes'/n/'narrative.md').read_bytes().decode('utf8') for n in self.order}
        self.root_id = next(n for n in self.order if self.nodes[n]['kind'] == 'root')
        if sum(m['kind']=='root' for m in self.nodes.values()) != 1:
            raise ValueError('Exactly one root required')
        if any(m['kind']=='scene' and m.get('state_mode')!='inherit' for m in self.nodes.values()):
            raise ValueError('This adapter requires inherited scene state; reset/prequel needs a separate conversion policy')
        self.baseline = load(self.root/'canon/baselines'/ (self.nodes[self.root_id]['state_base']['id']+'.json'))['state']
        if any(self.baseline.get(key) for key in ('world_facts','characters','relationships','character_memories','historical_traces','open_threads')):
            raise ValueError('Nonempty business root baseline needs explicit record conversion, not silent omission')
        self.turn_nodes = {v.get('turn_id'): n for n,v in self.inputs.items() if v.get('turn_id')}
        self.captures = {}
        for n,v in self.inputs.items():
            for message in v.get('raw_user_messages', []):
                if message.get('capture_id'): self.captures.setdefault(message['capture_id'], set()).add(n)
        for f in (self.root/'.system/commits').glob('*.json'):
            record = load(f)
            if record.get('node_id') in retained: self.turn_nodes.setdefault(f.stem, record['node_id'])
        self.hashes = {}
        for n in self.order:
            directory = self.root/'nodes'/n
            for name, expected in load(directory/'manifest.json')['files'].items():
                actual = digest((directory/name).read_bytes())
                if actual != expected: raise ValueError('Manifest mismatch: '+n+'/'+name)
                self.hashes['nodes/'+n+'/'+name] = actual

    def path(self, node):
        result=[]
        while node:
            if node in result: raise ValueError('Cyclic graph')
            result.append(node)
            node=self.all_nodes[node]['creation_parent_id']
        return list(reversed(result))

    def first_private(self, branch, anchor):
        path=self.paths[branch]
        if anchor not in path: raise ValueError('Backend anchor outside selected branch')
        candidates=[n for n in path[path.index(anchor)+1:] if self.all_nodes[n]['origin_branch_id']==branch]
        if not candidates: raise ValueError('No production scene for branch-private record')
        return candidates[0]

    def provenance(self, file, pointer, **extra):
        path=self.root/file
        # Derived identity/control labels identify conversions, not nonexistent source keys.
        original_pointer = '' if pointer == '/identity' else pointer[:-7] if pointer.endswith('/cancel') else pointer
        derived = {'conversion_address': pointer} if original_pointer != pointer else {}
        return {'source_file':file,'json_pointer':original_pointer,'source_sha256':digest(path.read_bytes()), **derived, **extra}

    def bind(self, value, file):
        """Prefer transaction evidence; parent-head fallback is branch/path constrained."""
        scope=value.get('scope', {})
        turn=scope.get('turn_id', value.get('turn_id'))
        if turn in self.turn_nodes:return self.turn_nodes[turn], 'turn/input/commit'
        explicit=value.get('node_id')
        if explicit in self.nodes:return explicit, 'explicit-node'
        for auxiliary in ('run.json','report.json'):
            other=self.root/Path(file).parent/auxiliary
            if other.is_file():
                record=load(other)
                if record.get('node_id') in self.nodes:return record['node_id'], auxiliary
        captures=[]
        user=value.get('user_input', {})
        for message in user.get('raw_messages', [])+user.get('rewrite_user_messages', []):
            captures.extend(self.captures.get(message.get('capture_id'), []))
        if captures and len(set(captures))==1:return captures[0], 'capture-id'
        branch=scope.get('branch_id', value.get('branch_id'))
        branch_path=self.paths.get(branch,[n for n in self.order if self.nodes[n]['origin_branch_id']==branch and self.nodes[n]['kind']=='scene'])
        if not branch_path:return None, 'unselected-or-unbound'
        body=value.get('literary_text')
        if body:
            matches=[n for n in branch_path if body==self.prose[n] or body in self.prose[n]]
            if len(matches)==1:return matches[0], 'published-text'
        anchor=scope.get('expected_head', value.get('expected_head'))
        children=[n for n in branch_path if self.nodes[n]['creation_parent_id']==anchor]
        if len(children)==1:return children[0], 'unique-child-on-declared-branch'
        return None, 'unresolved'

    def settings(self):
        value=deepcopy(self.story)
        for key in ('version','id','created_at','default_branch_id','default_canon_revision_id'):value.pop(key,None)
        if isinstance(value.get('protagonist'),dict):
            old_id=value['protagonist'].get('id')
            value['protagonist']['character_id']='player'
            if old_id: value['protagonist']['legacy_metadata_id']=old_id
        return value
