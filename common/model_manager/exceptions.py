class ModelLoadError(Exception):
    """Raised when a model fails to load."""

    pass


class ModelNotFoundError(Exception):
    """Raised when requesting a model key that is not registered."""

    pass


class ModelNotReadyError(Exception):
    """Raised when requesting a model that hasn't finished loading."""

    pass
