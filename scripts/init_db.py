"""Initialize the local database + vector table. Run once before first use:

    python scripts/init_db.py
"""
from tara.storage.db import connect, init_schema
from tara.storage.vector import init_vector_table


def main() -> None:
    init_schema()
    conn = connect()
    try:
        init_vector_table(conn)
    finally:
        conn.close()
    print("Initialized TaRa local store.")


if __name__ == "__main__":
    main()
