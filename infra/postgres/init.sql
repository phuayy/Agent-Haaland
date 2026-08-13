-- Extensions the schema depends on (migrations/versions/0001_core_schema.py
-- also declares these via CREATE EXTENSION IF NOT EXISTS; kept here too so a
-- fresh container is correct even before Alembic runs).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
