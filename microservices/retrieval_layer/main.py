from microservices.retrieval_layer.db.session import get_db_session
from sqlalchemy import text

def main():
    print("Starting retrieval layer DB check...")

    db = get_db_session()

    try:
        result = db.execute(text("SELECT 1")).fetchall()
        print("DB connection successful:", result)
    except Exception as e:
        print("DB connection FAILED:", e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
