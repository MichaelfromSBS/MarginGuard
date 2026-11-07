CREATE TABLE restaurant (
    id TEXT PRIMARY KEY CHECK(length(id) > 0),
    name TEXT NOT NULL CHECK(length(name) > 0),
    currency TEXT NOT NULL CHECK(length(currency) = 3 AND currency = upper(currency)),
    timezone TEXT NOT NULL,
    data_version INTEGER NOT NULL DEFAULT 0 CHECK(data_version >= 0),
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0, 1))
);

CREATE TABLE ingredients (
    id TEXT PRIMARY KEY CHECK(length(id) > 0),
    name TEXT NOT NULL,
    base_unit TEXT NOT NULL CHECK(base_unit IN ('lb', 'oz', 'each')),
    aliases_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(aliases_json))
);

CREATE TABLE dishes (
    id TEXT PRIMARY KEY CHECK(length(id) > 0),
    name TEXT NOT NULL
);

CREATE TABLE channels (
    id TEXT PRIMARY KEY CHECK(length(id) > 0),
    name TEXT NOT NULL,
    fee_rate TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(fee_rate) = 'text' AND CAST(fee_rate AS NUMERIC) BETWEEN 0 AND 1 AND length(fee_rate) > 0 AND fee_rate NOT GLOB '*[^0-9.]*' AND fee_rate NOT LIKE '.%' AND fee_rate NOT LIKE '%.' AND length(fee_rate) - length(replace(fee_rate, '.', '')) <= 1 AND (fee_rate = '0' OR substr(fee_rate, 1, 1) BETWEEN '1' AND '9' OR substr(fee_rate, 1, 2) = '0.') AND (instr(fee_rate, '.') = 0 OR length(fee_rate) - instr(fee_rate, '.') <= 8)),
    packaging_cost TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(packaging_cost) = 'text' AND CAST(packaging_cost AS NUMERIC) >= 0 AND length(packaging_cost) > 0 AND packaging_cost NOT GLOB '*[^0-9.]*' AND packaging_cost NOT LIKE '.%' AND packaging_cost NOT LIKE '%.' AND length(packaging_cost) - length(replace(packaging_cost, '.', '')) <= 1 AND (packaging_cost = '0' OR substr(packaging_cost, 1, 1) BETWEEN '1' AND '9' OR substr(packaging_cost, 1, 2) = '0.') AND (instr(packaging_cost, '.') = 0 OR length(packaging_cost) - instr(packaging_cost, '.') <= 8))
);

CREATE TABLE menu_prices (
    id TEXT PRIMARY KEY,
    dish_id TEXT NOT NULL REFERENCES dishes(id),
    channel_id TEXT NOT NULL REFERENCES channels(id),
    price TEXT NOT NULL CHECK(typeof(price) = 'text' AND CAST(price AS NUMERIC) >= 0 AND length(price) > 0 AND price NOT GLOB '*[^0-9.]*' AND price NOT LIKE '.%' AND price NOT LIKE '%.' AND length(price) - length(replace(price, '.', '')) <= 1 AND (price = '0' OR substr(price, 1, 1) BETWEEN '1' AND '9' OR substr(price, 1, 2) = '0.') AND (instr(price, '.') = 0 OR length(price) - instr(price, '.') <= 8)),
    effective_date TEXT NOT NULL,
    UNIQUE(dish_id, channel_id, effective_date)
);

CREATE TABLE recipe_versions (
    id TEXT PRIMARY KEY,
    dish_id TEXT NOT NULL REFERENCES dishes(id),
    effective_date TEXT NOT NULL,
    UNIQUE(dish_id, effective_date)
);

CREATE TABLE recipe_items (
    id TEXT PRIMARY KEY,
    recipe_version_id TEXT NOT NULL REFERENCES recipe_versions(id),
    ingredient_id TEXT NOT NULL REFERENCES ingredients(id),
    quantity TEXT NOT NULL CHECK(typeof(quantity) = 'text' AND CAST(quantity AS NUMERIC) > 0 AND length(quantity) > 0 AND quantity NOT GLOB '*[^0-9.]*' AND quantity NOT LIKE '.%' AND quantity NOT LIKE '%.' AND length(quantity) - length(replace(quantity, '.', '')) <= 1 AND (quantity = '0' OR substr(quantity, 1, 1) BETWEEN '1' AND '9' OR substr(quantity, 1, 2) = '0.') AND (instr(quantity, '.') = 0 OR length(quantity) - instr(quantity, '.') <= 8)),
    unit TEXT NOT NULL CHECK(unit IN ('lb', 'oz', 'each')),
    UNIQUE(recipe_version_id, ingredient_id)
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('invoice', 'receipt')),
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE CHECK(length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    media_type TEXT NOT NULL,
    source_text TEXT,
    status TEXT NOT NULL CHECK(status IN ('detected', 'processing', 'completed', 'needs_review', 'failed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0, 1)),
    error_code TEXT,
    error_message TEXT
);

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT
);

CREATE TABLE invoices (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
    vendor_id TEXT NOT NULL,
    vendor_name TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    currency TEXT NOT NULL CHECK(length(currency) = 3 AND currency = upper(currency)),
    subtotal TEXT NOT NULL CHECK(typeof(subtotal) = 'text' AND CAST(subtotal AS NUMERIC) >= 0 AND length(subtotal) > 0 AND subtotal NOT GLOB '*[^0-9.]*' AND subtotal NOT LIKE '.%' AND subtotal NOT LIKE '%.' AND length(subtotal) - length(replace(subtotal, '.', '')) <= 1 AND (subtotal = '0' OR substr(subtotal, 1, 1) BETWEEN '1' AND '9' OR substr(subtotal, 1, 2) = '0.') AND (instr(subtotal, '.') = 0 OR length(subtotal) - instr(subtotal, '.') <= 8)),
    tax TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(tax) = 'text' AND CAST(tax AS NUMERIC) >= 0 AND length(tax) > 0 AND tax NOT GLOB '*[^0-9.]*' AND tax NOT LIKE '.%' AND tax NOT LIKE '%.' AND length(tax) - length(replace(tax, '.', '')) <= 1 AND (tax = '0' OR substr(tax, 1, 1) BETWEEN '1' AND '9' OR substr(tax, 1, 2) = '0.') AND (instr(tax, '.') = 0 OR length(tax) - instr(tax, '.') <= 8)),
    freight TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(freight) = 'text' AND CAST(freight AS NUMERIC) >= 0 AND length(freight) > 0 AND freight NOT GLOB '*[^0-9.]*' AND freight NOT LIKE '.%' AND freight NOT LIKE '%.' AND length(freight) - length(replace(freight, '.', '')) <= 1 AND (freight = '0' OR substr(freight, 1, 1) BETWEEN '1' AND '9' OR substr(freight, 1, 2) = '0.') AND (instr(freight, '.') = 0 OR length(freight) - instr(freight, '.') <= 8)),
    total TEXT NOT NULL CHECK(typeof(total) = 'text' AND CAST(total AS NUMERIC) >= 0 AND length(total) > 0 AND total NOT GLOB '*[^0-9.]*' AND total NOT LIKE '.%' AND total NOT LIKE '%.' AND length(total) - length(replace(total, '.', '')) <= 1 AND (total = '0' OR substr(total, 1, 1) BETWEEN '1' AND '9' OR substr(total, 1, 2) = '0.') AND (instr(total, '.') = 0 OR length(total) - instr(total, '.') <= 8)),
    UNIQUE(vendor_id, invoice_number)
);

CREATE TABLE invoice_lines (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES invoices(id),
    ingredient_id TEXT REFERENCES ingredients(id),
    description TEXT NOT NULL,
    quantity TEXT NOT NULL CHECK(typeof(quantity) = 'text' AND CAST(quantity AS NUMERIC) > 0 AND length(quantity) > 0 AND quantity NOT GLOB '*[^0-9.]*' AND quantity NOT LIKE '.%' AND quantity NOT LIKE '%.' AND length(quantity) - length(replace(quantity, '.', '')) <= 1 AND (quantity = '0' OR substr(quantity, 1, 1) BETWEEN '1' AND '9' OR substr(quantity, 1, 2) = '0.') AND (instr(quantity, '.') = 0 OR length(quantity) - instr(quantity, '.') <= 8)),
    purchase_unit TEXT NOT NULL,
    pack_size TEXT CHECK(pack_size IS NULL OR (typeof(pack_size) = 'text' AND CAST(pack_size AS NUMERIC) > 0 AND length(pack_size) > 0 AND pack_size NOT GLOB '*[^0-9.]*' AND pack_size NOT LIKE '.%' AND pack_size NOT LIKE '%.' AND length(pack_size) - length(replace(pack_size, '.', '')) <= 1 AND (pack_size = '0' OR substr(pack_size, 1, 1) BETWEEN '1' AND '9' OR substr(pack_size, 1, 2) = '0.') AND (instr(pack_size, '.') = 0 OR length(pack_size) - instr(pack_size, '.') <= 8))),
    pack_unit TEXT,
    unit_price TEXT NOT NULL CHECK(typeof(unit_price) = 'text' AND CAST(unit_price AS NUMERIC) >= 0 AND length(unit_price) > 0 AND unit_price NOT GLOB '*[^0-9.]*' AND unit_price NOT LIKE '.%' AND unit_price NOT LIKE '%.' AND length(unit_price) - length(replace(unit_price, '.', '')) <= 1 AND (unit_price = '0' OR substr(unit_price, 1, 1) BETWEEN '1' AND '9' OR substr(unit_price, 1, 2) = '0.') AND (instr(unit_price, '.') = 0 OR length(unit_price) - instr(unit_price, '.') <= 8)),
    line_total TEXT NOT NULL CHECK(typeof(line_total) = 'text' AND CAST(line_total AS NUMERIC) >= 0 AND length(line_total) > 0 AND line_total NOT GLOB '*[^0-9.]*' AND line_total NOT LIKE '.%' AND line_total NOT LIKE '%.' AND length(line_total) - length(replace(line_total, '.', '')) <= 1 AND (line_total = '0' OR substr(line_total, 1, 1) BETWEEN '1' AND '9' OR substr(line_total, 1, 2) = '0.') AND (instr(line_total, '.') = 0 OR length(line_total) - instr(line_total, '.') <= 8)),
    source_page INTEGER NOT NULL DEFAULT 1 CHECK(source_page >= 1),
    source_text TEXT NOT NULL
);

CREATE TABLE ingredient_prices (
    id TEXT PRIMARY KEY,
    ingredient_id TEXT NOT NULL REFERENCES ingredients(id),
    invoice_line_id TEXT NOT NULL REFERENCES invoice_lines(id),
    effective_date TEXT NOT NULL,
    unit_cost TEXT NOT NULL CHECK(typeof(unit_cost) = 'text' AND CAST(unit_cost AS NUMERIC) >= 0 AND length(unit_cost) > 0 AND unit_cost NOT GLOB '*[^0-9.]*' AND unit_cost NOT LIKE '.%' AND unit_cost NOT LIKE '%.' AND length(unit_cost) - length(replace(unit_cost, '.', '')) <= 1 AND (unit_cost = '0' OR substr(unit_cost, 1, 1) BETWEEN '1' AND '9' OR substr(unit_cost, 1, 2) = '0.') AND (instr(unit_cost, '.') = 0 OR length(unit_cost) - instr(unit_cost, '.') <= 8)),
    base_unit TEXT NOT NULL CHECK(base_unit IN ('lb', 'oz', 'each')),
    UNIQUE(ingredient_id, invoice_line_id)
);

CREATE TABLE receipts (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
    receipt_number TEXT NOT NULL,
    channel_id TEXT REFERENCES channels(id),
    sold_at TEXT NOT NULL,
    local_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('completed', 'void', 'refund')),
    currency TEXT NOT NULL CHECK(length(currency) = 3 AND currency = upper(currency)),
    subtotal TEXT NOT NULL CHECK(typeof(subtotal) = 'text' AND CAST(subtotal AS NUMERIC) >= 0 AND length(subtotal) > 0 AND subtotal NOT GLOB '*[^0-9.]*' AND subtotal NOT LIKE '.%' AND subtotal NOT LIKE '%.' AND length(subtotal) - length(replace(subtotal, '.', '')) <= 1 AND (subtotal = '0' OR substr(subtotal, 1, 1) BETWEEN '1' AND '9' OR substr(subtotal, 1, 2) = '0.') AND (instr(subtotal, '.') = 0 OR length(subtotal) - instr(subtotal, '.') <= 8)),
    discount TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(discount) = 'text' AND CAST(discount AS NUMERIC) >= 0 AND length(discount) > 0 AND discount NOT GLOB '*[^0-9.]*' AND discount NOT LIKE '.%' AND discount NOT LIKE '%.' AND length(discount) - length(replace(discount, '.', '')) <= 1 AND (discount = '0' OR substr(discount, 1, 1) BETWEEN '1' AND '9' OR substr(discount, 1, 2) = '0.') AND (instr(discount, '.') = 0 OR length(discount) - instr(discount, '.') <= 8)),
    tax TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(tax) = 'text' AND CAST(tax AS NUMERIC) >= 0 AND length(tax) > 0 AND tax NOT GLOB '*[^0-9.]*' AND tax NOT LIKE '.%' AND tax NOT LIKE '%.' AND length(tax) - length(replace(tax, '.', '')) <= 1 AND (tax = '0' OR substr(tax, 1, 1) BETWEEN '1' AND '9' OR substr(tax, 1, 2) = '0.') AND (instr(tax, '.') = 0 OR length(tax) - instr(tax, '.') <= 8)),
    tip TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(tip) = 'text' AND CAST(tip AS NUMERIC) >= 0 AND length(tip) > 0 AND tip NOT GLOB '*[^0-9.]*' AND tip NOT LIKE '.%' AND tip NOT LIKE '%.' AND length(tip) - length(replace(tip, '.', '')) <= 1 AND (tip = '0' OR substr(tip, 1, 1) BETWEEN '1' AND '9' OR substr(tip, 1, 2) = '0.') AND (instr(tip, '.') = 0 OR length(tip) - instr(tip, '.') <= 8)),
    total TEXT NOT NULL CHECK(typeof(total) = 'text' AND CAST(total AS NUMERIC) >= 0 AND length(total) > 0 AND total NOT GLOB '*[^0-9.]*' AND total NOT LIKE '.%' AND total NOT LIKE '%.' AND length(total) - length(replace(total, '.', '')) <= 1 AND (total = '0' OR substr(total, 1, 1) BETWEEN '1' AND '9' OR substr(total, 1, 2) = '0.') AND (instr(total, '.') = 0 OR length(total) - instr(total, '.') <= 8)),
    UNIQUE(channel_id, receipt_number)
);

CREATE UNIQUE INDEX receipts_known_or_unknown_channel_key ON receipts(COALESCE(channel_id, ''), receipt_number);

CREATE TABLE receipt_items (
    id TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL REFERENCES receipts(id),
    dish_id TEXT NOT NULL REFERENCES dishes(id),
    description TEXT NOT NULL,
    quantity TEXT NOT NULL CHECK(typeof(quantity) = 'text' AND CAST(quantity AS NUMERIC) > 0 AND length(quantity) > 0 AND quantity NOT GLOB '*[^0-9.]*' AND quantity NOT LIKE '.%' AND quantity NOT LIKE '%.' AND length(quantity) - length(replace(quantity, '.', '')) <= 1 AND (quantity = '0' OR substr(quantity, 1, 1) BETWEEN '1' AND '9' OR substr(quantity, 1, 2) = '0.') AND (instr(quantity, '.') = 0 OR length(quantity) - instr(quantity, '.') <= 8)),
    unit_price TEXT NOT NULL CHECK(typeof(unit_price) = 'text' AND CAST(unit_price AS NUMERIC) >= 0 AND length(unit_price) > 0 AND unit_price NOT GLOB '*[^0-9.]*' AND unit_price NOT LIKE '.%' AND unit_price NOT LIKE '%.' AND length(unit_price) - length(replace(unit_price, '.', '')) <= 1 AND (unit_price = '0' OR substr(unit_price, 1, 1) BETWEEN '1' AND '9' OR substr(unit_price, 1, 2) = '0.') AND (instr(unit_price, '.') = 0 OR length(unit_price) - instr(unit_price, '.') <= 8)),
    gross_amount TEXT NOT NULL CHECK(typeof(gross_amount) = 'text' AND CAST(gross_amount AS NUMERIC) >= 0 AND length(gross_amount) > 0 AND gross_amount NOT GLOB '*[^0-9.]*' AND gross_amount NOT LIKE '.%' AND gross_amount NOT LIKE '%.' AND length(gross_amount) - length(replace(gross_amount, '.', '')) <= 1 AND (gross_amount = '0' OR substr(gross_amount, 1, 1) BETWEEN '1' AND '9' OR substr(gross_amount, 1, 2) = '0.') AND (instr(gross_amount, '.') = 0 OR length(gross_amount) - instr(gross_amount, '.') <= 8)),
    discount_amount TEXT NOT NULL DEFAULT '0.00' CHECK(typeof(discount_amount) = 'text' AND CAST(discount_amount AS NUMERIC) >= 0 AND length(discount_amount) > 0 AND discount_amount NOT GLOB '*[^0-9.]*' AND discount_amount NOT LIKE '.%' AND discount_amount NOT LIKE '%.' AND length(discount_amount) - length(replace(discount_amount, '.', '')) <= 1 AND (discount_amount = '0' OR substr(discount_amount, 1, 1) BETWEEN '1' AND '9' OR substr(discount_amount, 1, 2) = '0.') AND (instr(discount_amount, '.') = 0 OR length(discount_amount) - instr(discount_amount, '.') <= 8)),
    net_amount TEXT NOT NULL CHECK(typeof(net_amount) = 'text' AND CAST(net_amount AS NUMERIC) >= 0 AND length(net_amount) > 0 AND net_amount NOT GLOB '*[^0-9.]*' AND net_amount NOT LIKE '.%' AND net_amount NOT LIKE '%.' AND length(net_amount) - length(replace(net_amount, '.', '')) <= 1 AND (net_amount = '0' OR substr(net_amount, 1, 1) BETWEEN '1' AND '9' OR substr(net_amount, 1, 2) = '0.') AND (instr(net_amount, '.') = 0 OR length(net_amount) - instr(net_amount, '.') <= 8)),
    source_page INTEGER NOT NULL DEFAULT 1 CHECK(source_page >= 1),
    source_text TEXT NOT NULL
);

CREATE TABLE daily_coverage (
    date TEXT NOT NULL,
    channel_id TEXT NOT NULL REFERENCES channels(id),
    status TEXT NOT NULL CHECK(status IN ('complete', 'partial', 'unknown', 'closed')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(date, channel_id)
);

CREATE TABLE forecast_runs (
    id TEXT PRIMARY KEY,
    horizon_start TEXT NOT NULL,
    horizon_end TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'ready', 'insufficient_history', 'failed')),
    method TEXT NOT NULL,
    source_data_version INTEGER NOT NULL CHECK(source_data_version >= 0),
    assumptions_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(assumptions_json)),
    created_at TEXT NOT NULL,
    CHECK(horizon_start <= horizon_end)
);

CREATE TABLE forecast_values (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES forecast_runs(id),
    dish_id TEXT NOT NULL REFERENCES dishes(id),
    channel_id TEXT NOT NULL REFERENCES channels(id),
    units TEXT NOT NULL CHECK(typeof(units) = 'text' AND CAST(units AS NUMERIC) >= 0 AND length(units) > 0 AND units NOT GLOB '*[^0-9.]*' AND units NOT LIKE '.%' AND units NOT LIKE '%.' AND length(units) - length(replace(units, '.', '')) <= 1 AND (units = '0' OR substr(units, 1, 1) BETWEEN '1' AND '9' OR substr(units, 1, 2) = '0.') AND (instr(units, '.') = 0 OR length(units) - instr(units, '.') <= 8)),
    revenue TEXT NOT NULL CHECK(typeof(revenue) = 'text' AND CAST(revenue AS NUMERIC) >= 0 AND length(revenue) > 0 AND revenue NOT GLOB '*[^0-9.]*' AND revenue NOT LIKE '.%' AND revenue NOT LIKE '%.' AND length(revenue) - length(replace(revenue, '.', '')) <= 1 AND (revenue = '0' OR substr(revenue, 1, 1) BETWEEN '1' AND '9' OR substr(revenue, 1, 2) = '0.') AND (instr(revenue, '.') = 0 OR length(revenue) - instr(revenue, '.') <= 8)),
    ingredient_cost TEXT NOT NULL CHECK(typeof(ingredient_cost) = 'text' AND CAST(ingredient_cost AS NUMERIC) >= 0 AND length(ingredient_cost) > 0 AND ingredient_cost NOT GLOB '*[^0-9.]*' AND ingredient_cost NOT LIKE '.%' AND ingredient_cost NOT LIKE '%.' AND length(ingredient_cost) - length(replace(ingredient_cost, '.', '')) <= 1 AND (ingredient_cost = '0' OR substr(ingredient_cost, 1, 1) BETWEEN '1' AND '9' OR substr(ingredient_cost, 1, 2) = '0.') AND (instr(ingredient_cost, '.') = 0 OR length(ingredient_cost) - instr(ingredient_cost, '.') <= 8)),
    UNIQUE(run_id, dish_id, channel_id)
);

CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'critical')),
    status TEXT NOT NULL CHECK(status IN ('new', 'acknowledged', 'resolved')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(evidence_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE notification_outbox (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL REFERENCES alerts(id),
    status TEXT NOT NULL CHECK(status IN ('pending', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE seed_runs (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE INDEX invoice_lines_invoice_idx ON invoice_lines(invoice_id);
CREATE INDEX ingredient_prices_history_idx ON ingredient_prices(ingredient_id, effective_date);
CREATE INDEX receipt_items_receipt_idx ON receipt_items(receipt_id);
CREATE INDEX receipts_sales_date_idx ON receipts(local_date, channel_id, status);
CREATE INDEX documents_status_idx ON documents(status, created_at);
CREATE INDEX jobs_pending_idx ON processing_jobs(status, created_at);
CREATE INDEX alerts_status_idx ON alerts(status, created_at);
