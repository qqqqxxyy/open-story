from pathlib import Path
import json
from .contracts import validate


def load(path):
    path=Path(path).resolve()
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    validate(value,'config')
    location=Path(value['location'])
    if not location.is_absolute():location=path.parent/location
    return {**value,'location':str(location.resolve())}


def open_store(config):
    if config['backend']=='sqlite':
        from .backends.sqlite import SQLiteStore
        return SQLiteStore(config)
    from .backends.file import FileStore
    return FileStore(config)
