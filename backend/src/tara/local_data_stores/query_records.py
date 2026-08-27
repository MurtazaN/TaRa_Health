"""Row operations for the `queries` audit table (design §4, §7).

All SQL for this table lives here, as it does for documents and chunks. The
table has existed in db_schema since M2 with no record module, because nothing
answered a question yet.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from tara.data_models import Citation
from tara.local_data_stores.db_connection import connect_db

_INSERT_QUERY_ROW = """
INSERT INTO queries (
    query_id, question, retrieved_chunk_ids, answer, citations,
    safety_flag, model_route, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def insert_query_record(
    question: str,
    retrieved_chunk_ids: Sequence[str],
    answer: str,
    citations: Sequence[Citation],
    safety_flag: str,
    model_route: str,
) -> str:
    """Record one answered, declined, or escalated query. Returns the query id.

    `model_route` is the PHI-egress audit trail (§7): it records whether this
    particular answer's context left the device, which the generation_mode
    setting alone cannot tell you afterwards, because the setting may have
    changed since.
    """
    query_id = str(uuid.uuid4())
    conn = connect_db()
    try:
        conn.execute(
            _INSERT_QUERY_ROW,
            (
                query_id,
                question,
                json.dumps(list(retrieved_chunk_ids)),
                answer,
                json.dumps([citation.__dict__ for citation in citations]),
                safety_flag,
                model_route,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return query_id
