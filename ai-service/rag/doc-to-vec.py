# read the chunks from db, do embedding

from __future__ import annotations

import os
import urllib.parse
import psycopg2

import argparse

from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

def _connect():
    return psycopg2.connect(
        user=os.getenv("POSTGRES_USER", "rdtii_user"),
        dbname=os.getenv("POSTGRES_DB", "rdtii"),
        password=os.getenv("POSTGRES_PASSWORD","rdtii_password"),
        host=os.getenv("POSTGRES_HOST","localhost"),
        port=os.getenv("POSTGRES_PORT","5433"),
    )

def _fetch_pending(cur, limit: int | None):
    cur.execute(
        """
        SELECT dc.id, dc.chunk_text, ds.document_id, d.country_code
        FROM    document_chunks     dc
        JOIN    document_sections   ds ON dc.section_id     = ds.id
        JOIN    documents           d  ON ds.document_id    = d.id
        LEFT    JOIN chunk_embeddings ce ON ce.chunk_id     = dc.id
        WHERE   ce.id IS NULL
        ORDER   BY dc.id
        %s
        """ % ("LIMIT %d" % limit if limit else ""),
    )
    return cur.fetchall()


def _to_pgvector(vec) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--limit", type=int, default=None, help="cap total chunks this run")
    args = ap.parse_args()

    model = SentenceTransformer(MODEL_NAME)
    conn  = _connect()
    total = 0
    try:
        with conn.cursor() as cur:
            rows = _fetch_pending(cur, args.limit)
            print(f"{len(rows)} chunks are pending embedding")
            
            for i in range(0, len(rows), args.batch_size):
                batch = rows[i : i + args.batch_size]
                texts = [r[1] for r in batch]
                vecs  = normalize(model.encode(texts)) #L2

                records = [
                    (chunk_id, document_id, country_code, _to_pgvector(vec))
                    for (chunk_id, _txt, document_id, country_code), vec in zip(batch, vecs)
                ]
                execute_values(
                    cur,
                    "INSERT INTO chunk_embeddings "
                    "(chunk_id, document_id, country_code, embedding) "
                    "VALUES %s",
                    records,
                    template="(%s, %s, %s, %s::vector)",
                )
                conn.commit()
                total += len(records)
                print(f"  embedded {total}/{len(rows)}")
    finally:
        conn.close()
    print(f"done - {total} embeddings written")

if __name__ == "__main__":
    main()

