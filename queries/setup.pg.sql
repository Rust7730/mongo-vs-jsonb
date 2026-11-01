CREATE TABLE IF NOT EXISTS orders (id UUID PRIMARY KEY, data JSONB);
CREATE INDEX IF NOT EXISTS orders_timestamp_idx ON orders (((data->>'timestamp') COLLATE "C"));
