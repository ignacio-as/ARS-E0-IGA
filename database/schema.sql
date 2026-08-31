CREATE TABLE IF NOT EXISTS demands (
    id BIGSERIAL PRIMARY KEY,
    demand JSONB NOT NULL,
    demand_set JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS demands_origin_index
ON demands ((demand_set ->> 'idpk'), (demand ->> 'city'));

CREATE INDEX IF NOT EXISTS demands_city_index
ON demands ((demand ->> 'city'));

CREATE INDEX IF NOT EXISTS demands_received_at_index
ON demands (received_at DESC);
