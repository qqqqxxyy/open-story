"""Provision a storage configuration. No story settings or workflow states."""
from pathlib import Path
import json
from .contracts import DataError, validate


def provision_config(config_path: str | Path, config: dict) -> Path:
    """Create a config once; reuse an identical config without overwriting it."""
    path = Path(config_path).resolve()
    validate(config, 'config')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except FileExistsError:
        existing = json.loads(path.read_text(encoding='utf-8-sig'))
        validate(existing, 'config')
        if {k:v for k,v in existing.items() if k!='skill_version'} != {k:v for k,v in config.items() if k!='skill_version'}:
            raise DataError('STORE_CONFIG_CONFLICT', 'Existing storage configuration differs')
    return path
