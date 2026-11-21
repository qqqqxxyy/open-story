"""Public storage factory and abstract API. No workflow or CLI imports."""
from .base import DataStore
from .config import load, open_store

def connect(config_path) -> DataStore:
    store=open_store(load(config_path))
    try:
        store.initialize()
        return store
    except Exception:
        store.close()
        raise
