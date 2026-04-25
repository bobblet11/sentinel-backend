from microservices.retrieval_layer.db.session import ensure_schema_compatibility


def main():
    print("Ensuring retrieval tables and compatibility columns exist...")
    ensure_schema_compatibility()
    print("Done.")


if __name__ == "__main__":
    main()
