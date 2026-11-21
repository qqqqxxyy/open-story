"""Reserved file-backend adapter. Active implementations currently target SQLite."""
from ..contracts import DataError

class FileStore:
    def __init__(self,config):
        raise DataError('BACKEND_UNAVAILABLE','File backend is a reserved adapter; use SQLite')
