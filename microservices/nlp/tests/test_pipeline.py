import sys
import os
import json
import logging
import dataclasses
from pathlib import Path

# Adjusting path to find the workspace modules
# We need to add the workspace root to sys.path to resolve 'common' and 'microservices'
# Root is ../../../ relative to this file
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from common.models.api.redis_models import Article, NLPResult, NLPOptions
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.embedder import Embedder
from microservices.nlp.components.centrality import CentralityScorer
from microservices.nlp.components.bias import BiasDetector
from microservices.nlp.components.ner import EntityRecognizer
from microservices.nlp.components.checkworthy import CheckWorthinessFilter

def run_local_pipeline_test():
    # 1. Arrange: Load data from JSON
    json_path = os.path.join(os.path.dirname(__file__), 'article.json')
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    # Article(text=..., title=..., link=...) - based on nlp_service.py usage
    article = Article(
        title=data.get('title', 'Unknown Title'),
        text=data.get('text', ''),
        link=data.get('url', data.get('link', 'http://example.com'))
    )
    result = NLPResult()
    options = NLPOptions()

    # Initialize Components
    pre = Preprocessor()
    emb = Embedder()
    cen = CentralityScorer()
    bias = BiasDetector()
    ner = EntityRecognizer()
    chk = CheckWorthinessFilter()

    # 2. Act: Execute Pipeline Steps
    print(f"\n--- Testing Job: {article.link} ---")
    
    # Matching the order in nlp_service.py
    try:
        pre.run(article, result, options)
        print(f"✓ Preprocessed into {len(result.sentences) if result.sentences else 0} sentences.")

        emb.run(article, result, options)
        print("✓ Embeddings generated.")

        cen.run(article, result, options)
        print("✓ Centrality calculated.")

        bias.run(article, result, options)
        print("✓ Bias detection complete.")

        ner.run(article, result, options)
        print(f"✓ Found {len(result.entities_in_article)} entities.") 
        
        chk.run(article, result, options)
        print(f"✓ Claims extracted.")

    except Exception as e:
        print(f"Error during pipeline execution: {e}")
        import traceback
        traceback.print_exc()

    # 3. Assert / Inspect Results
    print("\n" + "="*50)
    print("FINAL ANALYSIS OUTPUT")
    print("="*50)
    
    if result.sentences:
        print(f"Total Sentences: {len(result.sentences)}")
        for i, s in enumerate(result.sentences): 
             # Print details for every sentence to debug classification
             print(f"Sent {i}: [{s.claim_type or 'N/A'}] ({s.confidence:.2f}) - Checkworthy: {s.is_checkworthy}")
             print(f"    Text: {s.text[:100]}...")

    print(f"\nTotal Claims Extracted: {len(result.claims_in_article)}")

    # Output as JSON
    output_file = Path(os.path.join(os.path.dirname(__file__), 'test_output.json'))
    
    with open(output_file, 'w') as out_f:
        json.dump(dataclasses.asdict(result), out_f, indent=2, default=str)
    print(f"\nFull output saved to '{output_file}'")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_local_pipeline_test()
