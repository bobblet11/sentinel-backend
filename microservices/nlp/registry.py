from microservices.nlp.models.base import (
    SentenceEmbedder,
    ZeroShotClassifier,
    NERModel,
    Seq2SeqRewriter,
)

class ModelRegistry:
    """
    Manages the lifecycle and loading of ML models.
    """
    def __init__(self):
        """
        Initialize the registry.
        """
        pass

    def get_embedder(self) -> SentenceEmbedder:
        """
        Returns the loaded sentence embedder model.
        
        Raises:
            ModelNotReadyError: If the model is not loaded.
        """
        raise NotImplementedError

    def get_zero_shot_classifier(self) -> ZeroShotClassifier:
        """
        Returns the loaded zero-shot classifier model.
        
        Raises:
            ModelNotReadyError: If the model is not loaded.
        """
        raise NotImplementedError

    def get_ner(self) -> NERModel:
        """
        Returns the loaded NER model.
        
        Raises:
            ModelNotReadyError: If the model is not loaded.
        """
        raise NotImplementedError

    def get_rewriter(self) -> Seq2SeqRewriter:
        """
        Returns the loaded sequence-to-sequence rewriter model.
        
        Raises:
            ModelNotReadyError: If the model is not loaded.
        """
        raise NotImplementedError

    def warmup(self) -> None:
        """
        Preloads all models into memory.
        """
        raise NotImplementedError
