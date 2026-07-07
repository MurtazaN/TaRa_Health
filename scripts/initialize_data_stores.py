"""Initialize the local database + vector table. Run once before first use:

    python scripts/initialize_data_stores.py
"""
from tara.local_data_stores.db_connection import connect_db
from tara.local_data_stores.db_schema import init_db_schema
from tara.local_data_stores.vector_index import init_vector_table


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
