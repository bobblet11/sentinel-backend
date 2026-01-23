# microservices/nlp/nlp_service.py
from typing import List
from common.models.api.redis_models import Article, NLPOptions, NLPResult, StreamMessage
from common.service.service_template import ProcessingError, ServiceConfig, ServiceTemplate

from microservices.nlp.models.base import NLPComponent

# We will implement these empty skeletons in the next step
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.centrality import CentralityScorer
from microservices.nlp.components.bias import BiasDetector
from microservices.nlp.components.ner import EntityRecognizer
# from microservices.nlp.components.checkworthy import ClaimExtractor

class NLPService(ServiceTemplate):

    def __init__(self, config:ServiceConfig, options: NLPOptions) -> None:
        super().__init__(config)
        
        self.options = options or NLPOptions()        
        
        # Define the execution order of the pipeline
        self.pipeline: List[NLPComponent] = [
            Preprocessor(),
            CentralityScorer(),
            BiasDetector(),
            EntityRecognizer(),
            # ClaimExtractor()
        ]
    
    
    def _analyze_html_and_update(self, message: StreamMessage) -> StreamMessage:
        """
        The main orchestrator that passes the article through each pipeline stage.
        """
        article = Article(text=message.text, title=message.title, link=message.link)
        analysis_result = NLPResult()

        for component in self.pipeline:
            try:
                component.run(article, analysis_result, self.options)                
            except Exception as e:
                print(f"Pipeline error in {component.__class__.__name__}: {str(e)}")
                raise
            
        message.set_nlp_result(analysis_result)
        return message


    def _process_message(self, message: StreamMessage) -> StreamMessage:
        try:
            analyzed_message:StreamMessage = self._analyze_html_and_update(message)
            return analyzed_message
        except Exception as e:
            raise ProcessingError(f"Failed to analyze {message.link}: {e}")
        
 