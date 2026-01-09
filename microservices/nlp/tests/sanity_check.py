import sys
import os
import inspect

# 1. SETUP PATH
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print(f"Checking environment...")
print(f"Root dir set to: {parent_dir}")

def run_sanity_check():
    print("\n--- STEP 1: Import Check ---")
    try:
        # Now importing from schemas.py
        import schemas as nlp_schemas
        print(f"✅ Successfully imported local 'schemas.py' from {nlp_schemas.__file__}")

    except ImportError as e:
        print(f"❌ Failed to import schemas.py: {e}")
        return

    print("\n--- STEP 2: Structure Inspection ---")
    # Inspect the classes inside schemas.py
    classes = [m[0] for m in inspect.getmembers(nlp_schemas, inspect.isclass) if m[1].__module__ == nlp_schemas.__name__]
    
    if not classes:
        print("❌ No classes found in schemas.py. Did you save the file?")
        return
    
    print(f"Found classes: {classes}")

    print("\n--- STEP 3: Embeddings Verification ---")
    found_embedding = False
    
    for cls_name in classes:
        cls_obj = getattr(nlp_schemas, cls_name)
        annotations = getattr(cls_obj, '__annotations__', {})
        
        # Check for embedding fields
        if 'embedding' in annotations or 'embeddings' in annotations:
            print(f"   ✅ '{cls_name}' has an embedding field.")
            found_embedding = True
        else:
            print(f"   ℹ️  '{cls_name}' does not have an explicit embedding field.")

    if found_embedding:
        print("\n🎉 SANITY CHECK PASSED: Structure exists and embeddings are accounted for.")
    else:
        print("\n⚠️  WARNING: No 'embedding' field detected. Ensure you added it for PGVector support.")

if __name__ == "__main__":
    run_sanity_check()
