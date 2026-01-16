import sys
import os
import logging

# 1. SETUP PATH so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 2. IMPORTS
from registry import registry
from schemas import ArticleInput, AnalysisResult, AnalysisOptions
from components.preprocess import Preprocessor
from components.embedder import Embedder
from components.dedupe import Deduplicator
from components.centrality import CentralityScorer
from components.ner import EntityRecognizer
from components.bias import BiasDetector

# Configure Logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_full_chain():
    print("\nSTARTING PIPELINE TEST\n")

    # --- SETUP DATA ---
    text_content = (
        "Artificial Intelligence is transforming modern healthcare. "
        "Doctors are using AI to diagnose diseases faster. "
        "AI is revolutionizing the medical field. "  # Semantic duplicate of sentence 1
        "Google and Microsoft are investing heavily in these technologies. "
        "However, privacy concerns remain a major issue."
    )

    article = ArticleInput(
        id="test-doc-001", 
        url="http://test.com/ai-healthcare", 
        text=text_content
    )

    result = AnalysisResult(article_id=article.id)
    
    options = AnalysisOptions()

    # --- STEP 1: PREPROCESSING ---
    print("--- 1. Preprocessing ---")
    pre = Preprocessor()
    pre.run(article, result, options)
    print(f"   Split into {len(result.sentences)} sentences.")

    # --- STEP 2: EMBEDDING ---
    print("\n--- 2. Embedding ---")
    # Load model from registry singleton
    embedder = Embedder(embedding_model=registry.embeddings)
    embedder.run(article, result, options)
    
    # Validation check
    if result.sentences and result.sentences[0].embedding:
        dim = len(result.sentences[0].embedding)
        print(f"  Embeddings generated (Dimension: {dim}).")
    else:
        print("   Embedding generation failed.")

    # --- STEP 3: DEDUPLICATION ---
    print("\n--- 3. Deduplication ---")
    initial_count = len(result.sentences)
    dedupe = Deduplicator(threshold=0.75) # High enough to catch the duplicate
    dedupe.run(article, result, options)
    final_count = len(result.sentences)
    
    if final_count < initial_count:
        print(f"   Removed {initial_count - final_count} duplicate sentences.")
    else:
        print("   No duplicates found.")

    # --- STEP 4: CENTRALITY SCORING ---
    print("\n--- 4. Centrality Scoring ---")
    centrality = CentralityScorer()
    centrality.run(article, result, options)
    
    # Sort by score to see top sentences
    top_sentences = sorted(result.sentences, key=lambda x: x.score, reverse=True)
    print(f"   Top Sentence: \"{top_sentences[0].text}\" (Score: {top_sentences[0].score:.4f})")

    # --- STEP 5: ENTITY RECOGNITION (NER) ---
    print("\n--- 5. Entity Recognition ---")
    ner = EntityRecognizer(ner_model=registry.ner)
    ner.run(article, result, options)
    
    print(f"   Found {len(result.entities)} entities:")
    for ent in result.entities:
        print(f"      - {ent.text} ({ent.label})")


if __name__ == "__main__":
    test_full_chain()