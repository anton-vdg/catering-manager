-- ================================================================
-- schema.sql – die Struktur der Datenbank
-- Wird von init_db() in app.py eingespielt. Alle Befehle sind so
-- geschrieben, dass mehrfaches Ausführen nichts kaputt macht.
-- ================================================================

-- Eine Kategorie bündelt Produkte, z. B. "Braten" oder "Suppen".
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  -- UNIQUE: jeder Kategoriename darf nur einmal vorkommen.
  name TEXT NOT NULL UNIQUE,
  -- sort_order bestimmt die Reihenfolge auf der Seite (klein = oben).
  -- 10er-Schritte, damit man später etwas dazwischen schieben kann.
  sort_order INTEGER NOT NULL DEFAULT 0
);

-- Alle verkaufbaren Artikel.
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  -- Preise in CENT (18,00 € = 1800). Ganzzahlen vermeiden Rundungsfehler,
  -- die bei Kommazahlen (FLOAT) entstehen.
  price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
  -- Einheit für die Anzeige: "pro Stück", "pro Kilo", "pro Person" ...
  unit TEXT NOT NULL DEFAULT 'Stück',
  -- Steuersatz in Prozent. 7 = Speisen (ermäßigt), 19 = Non-Food.
  -- CHECK lässt nur diese zwei Werte zu.
  tax_rate INTEGER NOT NULL CHECK (tax_rate IN (7, 19)) DEFAULT 19,
  -- 1 = sichtbar, 0 = "gelöscht". Es wird nie wirklich gelöscht,
  -- weil alte Bestellungen auf das Produkt verweisen.
  active INTEGER NOT NULL DEFAULT 1,
  -- NULL = noch keiner Kategorie zugeordnet.
  -- ON DELETE SET NULL: Kategorie löschen setzt die Produkte auf
  -- "ohne Kategorie", statt sie mitzulöschen.
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  -- NULL = normales Produkt. Zahl = Sammelprodukt für so viele Personen.
  bundle_persons INTEGER
);

-- Was ein Sammelprodukt enthält. quantity_per_person = Stück pro Person.
CREATE TABLE IF NOT EXISTS bundle_items (
  bundle_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  component_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  quantity_per_person INTEGER NOT NULL DEFAULT 1 CHECK (quantity_per_person > 0),
  PRIMARY KEY (bundle_id, component_id)
);

-- Verhindert doppelte Produktnamen (exakt gleich geschrieben).
-- Wird beim Import in produktliste.sql gebraucht: "INSERT OR IGNORE"
-- überspringt eine Zeile, wenn der Name schon existiert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_name ON products(name);

-- Ein Auftrag mit Kundendaten, Termin und Art der Übergabe.
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY,
  customer_name TEXT NOT NULL,
  customer_phone TEXT NOT NULL,
  delivery_address TEXT,          -- darf leer sein, daher kein NOT NULL
  order_date TEXT NOT NULL,       -- Format "2026-11-12"
  order_time TEXT NOT NULL,       -- Format "18:30"
  -- Nur diese zwei Werte sind erlaubt.
  fulfillment_type TEXT NOT NULL
    CHECK (fulfillment_type IN ('abholung', 'lieferung')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  notes TEXT                     -- freie Notiz zur Bestellung, darf leer sein
);

-- Die einzelnen Positionen einer Bestellung.
CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  -- WICHTIG: der Preis zum Zeitpunkt der Bestellung, kopiert aus products.
  -- Ändert sich der Produktpreis später, bleibt diese Rechnung korrekt.
  unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
  -- NULL = normale Position. Sonst die ID des Büfetts, zu dem diese Position gehört.
  bundle_id INTEGER,
  -- Wird der Auftrag gelöscht, verschwinden seine Positionen automatisch mit.
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  -- Ein Produkt, das in einer Bestellung vorkommt, kann nicht gelöscht werden.
  -- (In der App wird ohnehin nur "active = 0" gesetzt, das ist das Netz darunter.)
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
);

-- Beschleunigt das Laden der Tagesansicht: get_orders_for_day() sucht
-- ständig nach "WHERE order_id = ?". Ohne Index müsste SQLite jedes Mal
-- die ganze Tabelle durchgehen.
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- Beschleunigt das Laden der Tagesansicht ebenfalls:
-- "WHERE order_date = ?"
CREATE INDEX IF NOT EXISTS idx_orders_order_date ON orders(order_date);

-- Kundenstamm für die Autovervollständigung auf der Bestellseite.
-- Ein Kunde ist durch Name + Telefonnummer eindeutig (Groß-/Kleinschreibung
-- beim Namen egal). Die Bestellungen kopieren die Daten weiterhin selbst,
-- damit alte Aufträge unverändert bleiben.
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL COLLATE NOCASE,
  phone TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  UNIQUE (name, phone)
);