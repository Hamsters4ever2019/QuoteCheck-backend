CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    postcode TEXT
);

CREATE TABLE IF NOT EXISTS job_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    default_hours REAL,
    default_materials REAL,
    default_travel REAL
);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(id),
    job_type_id INTEGER REFERENCES job_types(id),
    estimated_hours REAL NOT NULL,
    materials_cost REAL NOT NULL,
    travel_distance REAL NOT NULL,
    hourly_rate REAL NOT NULL,
    vehicle_cost_per_mile REAL NOT NULL,
    overhead_pct REAL NOT NULL,
    target_margin_pct REAL NOT NULL,
    quote_price REAL NOT NULL,
    labour_cost REAL NOT NULL,
    travel_cost REAL NOT NULL,
    subtotal REAL NOT NULL,
    overhead REAL NOT NULL,
    total_cost REAL NOT NULL,
    required_quote REAL NOT NULL,
    profit REAL NOT NULL,
    actual_margin REAL NOT NULL,
    verdict TEXT NOT NULL,
    shortfall REAL NOT NULL,
	headroom REAL NOT NULL DEFAULT 0,
	workings TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS actuals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id INTEGER NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    actual_hours REAL NOT NULL,
    actual_materials REAL NOT NULL,
    actual_travel REAL NOT NULL,
    actual_cost REAL NOT NULL,
    actual_profit REAL NOT NULL,
    actual_margin REAL NOT NULL,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quotes_created ON quotes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_actuals_quote ON actuals(quote_id);