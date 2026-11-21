"""Map an initialization target to a data configuration and repository."""
from pathlib import Path
from script.data.api import connect
from script.data.resources import provision_config
from .repositories import Repository


class StoryStores:
    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root).resolve()

    def provision(self, story_id: str, environment: str) -> tuple[Repository, dict]:
        folder = self.data_root / environment / story_id
        config_path = provision_config(folder / 'sqlite.json', {
            'database_id': story_id,
            'backend': 'sqlite',
            'location': 'story.sqlite3',
            'busy_timeout_ms': 5000,
        })
        repository = Repository(connect(config_path))
        return repository, {
            'config_path': str(config_path),
            'database_path': str((folder / 'story.sqlite3').resolve()),
        }
