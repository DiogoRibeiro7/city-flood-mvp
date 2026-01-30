-- Enables extensions in the target DB.
-- The TimescaleDB HA image pre-installs extensions, but they must be enabled per database.

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Helpful for JSONB / text search in real projects, harmless here:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
