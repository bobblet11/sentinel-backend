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

def run_local_pipeline_test(filename="article.json"):
    # 1. Arrange: Load data from JSON
    json_path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    # Article(text=..., title=..., link=...) - mapping updated JSON structure to internal model
    article = Article(
        title=data.get('article_title', 'Unknown Title'),
        text=data.get('article_text', ''),
        # Map 'article_url' from JSON to the Article's 'link' field
        link=data.get('article_url', 'http://example.com'),
        summary=data.get('article_summary', '')
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
             print(f"Sent {i}: [{s.claim_type or 'N/A'}] (Conf: {s.confidence:.2f} | Centrality: {s.score:.4f}) - Checkworthy: {s.is_checkworthy}")
             print(f"    Text: {s.text}...")

    print(f"\nTotal Claims Extracted: {len(result.claims_in_article)}")

    # Output as JSON
    # If the input was article5.json, output is test_output_article5.json
    base_name = os.path.splitext(filename)[0]
    output_filename = f"test_output_{base_name}.json" if filename != 'article.json' else 'test_output.json'
    output_file = Path(os.path.join(os.path.dirname(__file__), output_filename))
    
    with open(output_file, 'w') as out_f:
        json.dump(dataclasses.asdict(result), out_f, indent=2, default=str)
    print(f"\nFull output saved to '{output_file}'")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    target_file = 'article.json'
    if len(sys.argv) > 1:
        # User provides just the number, e.g. "5" -> "article5.json"
        target_file = f"article{sys.argv[1]}.json"

    run_local_pipeline_test(target_file)
