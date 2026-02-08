import json
import os

def strip_embeddings(input_path, output_path=None):
    """
    Reads an NLP output JSON and removes all 'embedding' keys from 
    sentences, claims, and the global document level.
    """
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return

    # 1. Load the long JSON
    with open(input_path, 'r') as f:
        data = json.load(f)

    # 2. Strip Global Embedding
    if 'doc_embedding' in data:
        data['doc_embedding'] = "[STRIPPED]"

    # 3. Strip Sentence-level Embeddings
    if 'sentences' in data:
        for sentence in data['sentences']:
            if 'embedding' in sentence:
                sentence['embedding'] = "[STRIPPED]"

    # 4. Strip Claim-level Embeddings
    if 'claims' in data:
        for claim in data['claims']:
            if 'embedding' in claim:
                claim['embedding'] = "[STRIPPED]"

    # 5. Save the readable version
    if output_path is None:
        output_path = input_path.replace(".json", "_readable.json")

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Successfully stripped embeddings. Readable file saved to: {output_path}")

if __name__ == "__main__":
    # You can point this to your 'test_output.json'
    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_file = os.path.join(current_dir, 'test_output.json')
    strip_embeddings(target_file)