"""In-memory resources, bound by the caller. This module does not load configuration."""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from .errors import ContractError

_current = ContextVar('openstory_resources', default=None)

@dataclass
class RuntimeResources:
    project_root: object
    settings: dict
    schemas: dict
    relation_rules: dict
    operations: dict
    errors: dict
    validator: object
    logger: object
    handlers: dict = field(default_factory=dict)

def peek():
    return _current.get()

def current():
    resources = _current.get()
    if resources is None:
        raise ContractError('RUNTIME_NOT_READY', 'Caller must bootstrap or supply runtime resources before storage/workflow use')
    return resources

def install(resources):
    _current.set(resources)
    return resources

@contextmanager
def using(resources):
    token = _current.set(resources)
    try:
        yield resources
    finally:
        _current.reset(token)

class SchemaView(Mapping):
    """Stable handles keep imports independent of initialization order."""
    def __init__(self, name):
        self.name = name
    def __getitem__(self, key):
        return current().schemas[self.name][key]
    def __iter__(self):
        return iter(current().schemas[self.name])
    def __len__(self):
        return len(current().schemas[self.name])

DATA = SchemaView('data')
WORKFLOW = SchemaView('workflow')
AGENT = SchemaView('agent')
