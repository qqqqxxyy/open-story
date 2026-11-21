"""Stable exceptions backed by the caller-loaded error catalog; no file IO."""

class ContractError(ValueError):
    def __init__(self, code, message, details=None):
        from .runtime import peek
        resources=peek()
        self.code=code
        self.details=details
        self.definition=resources.errors.get(code,{}) if resources is not None else {}
        super().__init__(message)
