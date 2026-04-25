class ModelLoadError(Exception):
    """Raised when a model fails to load."""


class ModelNotFoundError(Exception):
    """Raised when requesting a model key that is not registered."""


class ModelNotReadyError(Exception):
    """Raised when requesting a model that hasn't finished loading."""
