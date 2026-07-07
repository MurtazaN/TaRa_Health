"""Initialize the local database + vector table. Run once before first use:

    python scripts/init_db.py
"""
from tara.storage.metadata_db import connect_db, init_db_schema
from tara.storage.vector_index import init_vector_table


def main() -> None:
    init_db_schema()
    conn = connect_db()
    try:
        init_vector_table(conn)
    finally:
        conn.close()
    print("Initialized TaRa local store.")


if __name__ == "__main__":
    main()
