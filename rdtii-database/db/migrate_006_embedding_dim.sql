-- migrate_006_embedding_dim.sql -MiniLM-384
ALTER TABLE chunk_embeddings ALTER COLUMN embedding TYPE vector(384);
DROP INDEX IF EXISTS idx_chunk_embeddings_embedding;
CREATE INDEX idx_chunk_embeddings_embedding
    ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
