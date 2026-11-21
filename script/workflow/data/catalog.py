"""Descriptor mapping and managed repository resources; no domain callbacks."""
from contextlib import contextmanager
from script.data.catalog import configurations
from script.data.api import connect
from .repositories import Repository


def descriptors(data_root, environment=None):
    return configurations(data_root,environment)


@contextmanager
def open_metadata(config_path):
    repository=Repository(connect(config_path))
    try:yield repository
    finally:repository.close()
