-- Eine Kategorie bündelt Produkte, z. B. "Braten" oder "Suppen".
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  -- Reihenfolge auf der Seite (klein = oben). 10er-Schritte, damit man
  -- später etwas dazwischen schieben kann.
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
  unit TEXT NOT NULL DEFAULT 'Stück',
  tax_rate INTEGER NOT NULL CHECK (tax_rate IN (7, 19)) DEFAULT 19,
  active INTEGER NOT NULL DEFAULT 1,
  -- NULL = noch keiner Kategorie zugeordnet.
  -- ON DELETE SET NULL: Kategorie löschen setzt die Produkte auf
  -- "ohne Kategorie", statt sie mitzulöschen.
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL
);

-- Verhindert doppelte Produktnamen. Wird beim Import gebraucht:
-- existiert der Name schon, wird die Zeile übersprungen.
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_name ON products(name);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY,
  customer_name TEXT NOT NULL,
  customer_phone TEXT NOT NULL,
  delivery_address TEXT,
  order_date TEXT NOT NULL,
  order_time TEXT NOT NULL,
  fulfillment_type TEXT NOT NULL CHECK (fulfillment_type IN ('abholung', 'lieferung')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
);