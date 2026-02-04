from microservices.retrieval_layer.models import Base
from microservices.retrieval_layer.db.session import engine

def main():
    print("Creating tables in DB (if missing)...")
    Base.metadata.create_all(engine)
    print("Done.")

if __name__ == "__main__":
    main()
