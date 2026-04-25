class NLPError(Exception):
    """
    Base exception for all errors originating from the NLP service.
    """

class InvalidInputError(NLPError):
    """
    Raised when the input provided to the NLP service is invalid or malformed.
    """

class ModelNotReadyError(NLPError):
    """
    Raised when a requested model is not loaded or available.
    """

class PipelineExecutionError(NLPError):
    """
    Raised when an error occurs during the execution of the NLP pipeline stages.
    """
