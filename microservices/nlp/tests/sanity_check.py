import sys
import os
import inspect

# 1. SETUP PATH
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add root workspace to path to support 'common' imports
root_dir = os.path.abspath(os.path.join(current_dir, '../../..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

print(f"Checking environment...")
print(f"Root dir set to: {root_dir}")

def run_sanity_check():
    print("\n--- STEP 1: Import Check ---")
    try:
        # Checking for common models
        from common.models.api import redis_models
        print(f"✅ Successfully imported 'common.models.api.redis_models' from {redis_models.__file__}")
        
    except ImportError as e:
        print(f"❌ Failed to import common.models.api.redis_models: {e}")
        return

    print("\n--- STEP 2: Structure Inspection ---")
    # Inspect the classes inside redis_models
    classes = [m[0] for m in inspect.getmembers(redis_models, inspect.isclass) if m[1].__module__ == redis_models.__name__]
    
    if not classes:
        print("❌ No classes found in redis_models.py.")
        return
    
    print(f"Found classes: {classes}")

    print("\n--- STEP 3: Embeddings Verification ---")
    found_embedding = False
    
    for cls_name in classes:
        cls_obj = getattr(redis_models, cls_name)
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
