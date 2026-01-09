import sys
import os
import torch

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from registry import registry

def test_loading():
    print("--- Testing Model Registry ---")
    
    # 1. Test NER
    print("\n1. Requesting NER pipeline...")
    ner = registry.ner
    result = ner("Apple Inc. is located in California.")
    print(f"   NER Result: {result}")
    assert len(result) > 0, "NER failed to find entities"

    # 2. Test Embeddings
    print("\n2. Requesting Embedding model...")
    embedder = registry.embeddings
    vector = embedder.encode("This is a test sentence.")
    print(f"   Vector shape: {vector.shape}")
    assert vector.shape[0] > 0, "Embedding failed"

    print("\n✅ Registry test passed!")

if __name__ == "__main__":
    test_loading()