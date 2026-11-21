"""Discover storage descriptors only; no creative business interpretation."""
from pathlib import Path
import json


def configurations(data_root, environment=None):
    root=Path(data_root).resolve()
    environments=[environment] if environment else ['debug','online']
    result=[]
    for label in environments:
        base=root/label
        if not base.exists():continue
        for path in sorted(base.glob('*/sqlite.json')):
            config=json.loads(path.read_text(encoding='utf-8-sig'))
            location=Path(config['location'])
            if not location.is_absolute():location=path.parent/location
            if location.exists(): result.append({'config_path':str(path.resolve()),'environment':label,'folder':path.parent.name})
    return result
