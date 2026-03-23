class ModelManagerError(Exception):
    """Base exception for model manager errors."""


class ModelNotFoundError(ModelManagerError):
    """Raised when a model key cannot be found in the lock file."""


class ModelDownloadError(ModelManagerError):
    """Raised when a model artifact cannot be downloaded or validated."""


class ModelLockTimeoutError(ModelManagerError):
    """Raised when waiting for a model lock times out."""
