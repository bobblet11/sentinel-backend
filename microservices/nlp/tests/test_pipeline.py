import sys
import os
import json
import logging
import dataclasses
from pathlib import Path

# Adjusting path to find the microservice modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from schemas import ArticleInput, AnalysisResult, AnalysisOptions
from components.preprocess import Preprocessor
from components.decontext import Decontextualizer
from components.checkworthy import CheckWorthinessFilter
from components.ner import EntityRecognizer
from components.embedder import Embedder
from components.centrality import CentralityScorer
from components.dedupe import Deduplicator

def run_local_pipeline_test():
    # 1. Arrange: Load data from JSON
    json_path = os.path.join(os.path.dirname(__file__), 'article.json')
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    article = ArticleInput(
        id=data['job_id'],
        title=data['title'],
        text=data['text'],
        url=data['url']
    )
    result = AnalysisResult(article_id=article.id)
    options = AnalysisOptions()

    # Initialize Components
    pre = Preprocessor()
    dec = Decontextualizer()
    chk = CheckWorthinessFilter()
    ner = EntityRecognizer()
    emb = Embedder()
    cen = CentralityScorer()
    ded = Deduplicator()

    # 2. Act: Execute Pipeline Steps
    print(f"\n--- Testing Job: {article.id} ---")
    
    pre.run(article, result, options)
    print(f"✓ Preprocessed into {len(result.sentences)} sentences.")

    dec.run(article, result, options)
    print("✓ Decontextualization applied.")

    chk.run(article, result, options)
    print(f"✓ Check-worthiness score assigned.")

    ner.run(article, result, options)
    print(f"✓ Found {len(result.entities)} entities.")

    emb.run(article, result, options)
    cen.run(article, result, options)
    print("✓ Embeddings and Centrality calculated.")

    ded.run(article, result, options)
    print("✓ Deduplication complete.")

    # 3. Assert / Inspect Results
    print("\n" + "="*50)
    print("FINAL ANALYSIS OUTPUT")
    print("="*50)
    
    for i, s in enumerate(result.sentences):
        worthy_tag = "[CLAIM]" if s.is_checkworthy else "[INFO]"
        print(f"{worthy_tag} Sent {i} (Centrality: {s.score:.2f}):")
        print(f"  Text: {s.text}")
        if hasattr(s, 'entities') and s.entities:
            print(f"  Entities: {[e.text for e in s.entities]}")
        print("-" * 30)

    # Output as JSON only if the file does not already exist
    output_file = Path('test_output.json')
    if not output_file.exists():
        output_dict = dataclasses.asdict(result)
        with open(output_file, 'w') as out_f:
            json.dump(output_dict, out_f, indent=2)
        print(f"\nFull output saved to '{output_file}'")
    else:
        print(f"\nSkipping write: '{output_file}' already exists.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_local_pipeline_test()