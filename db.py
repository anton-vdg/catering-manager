import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import date

DB_PATH = Path("partyservice.db")
SCHEMA_PATH = Path("schema.sql")


# ------------------------------------------------------------
# Verbindungs-Helper: Transaktion + Foreign Keys aktivieren
# ------------------------------------------------------------
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------------------------------------
# Datenbank-Schema initialisieren
# ------------------------------------------------------------
def init_db():
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(schema_sql)


# ------------------------------------------------------------
# Kunden: anlegen oder aktualisieren
# Logik: wenn Telefon vorhanden und existiert -> update, sonst insert
# ------------------------------------------------------------
def upsert_customer(name: str, phone: str | None, address: str | None) -> int:
    phone_norm = (phone or "").strip() or None
    address = (address or "").strip() or None
    name = (name or "").strip() or "Unbekannt"

    with get_conn() as conn:
        if phone_norm:
            row = conn.execute("SELECT id FROM customers WHERE phone = ?", (phone_norm,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE customers SET name=?, address=? WHERE id=?",
                    (name, address, row["id"]),
                )
                return int(row["id"])

        cur = conn.execute(
            "INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)",
            (name, phone_norm, address),
        )
        return int(cur.lastrowid)



# ------------------------------------------------------------
# Produktliste / Artikelstamm
# ------------------------------------------------------------
def create_product(
    name: str,
    default_unit_price_cents: int,
    default_vat_rate: float,
    default_unit: str,
    default_quantity: float,
    sku: str | None = None,
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Produktname darf nicht leer sein.")

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO products (sku, name, default_quantity, default_unit, default_vat_rate, default_unit_price_cents)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (sku or "").strip() or None,
                name,
                float(default_quantity),
                (default_unit or "Stk").strip() or "Stk",
                float(default_vat_rate),
                int(default_unit_price_cents),
            ),
        )
        return int(cur.lastrowid)
        


def list_products(active_only: bool = True) -> list[dict]:
    with get_conn() as conn:
        if active_only:
            rows = conn.execute(
                """
                SELECT id, sku, name, default_quantity, default_unit,
                       default_vat_rate, default_unit_price_cents, is_active
                FROM products
                WHERE is_active = 1
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, sku, name, default_quantity, default_unit,
                       default_vat_rate, default_unit_price_cents, is_active
                FROM products
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]


def get_product(product_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, sku, name, default_quantity, default_unit,
                   default_vat_rate, default_unit_price_cents, is_active
            FROM products
            WHERE id = ?
            """,
            (product_id,),
        ).fetchone()
        if not row:
            raise ValueError("Produkt nicht gefunden.")
        return dict(row)


def set_product_active(product_id: int, is_active: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, int(product_id)),
        )


# ------------------------------------------------------------
# Bestellung anlegen (Kopf + Positionen)
# Positionen speichern immer Snapshot von Text/Preis/MwSt
# ------------------------------------------------------------
def create_order(
    customer_id: int | None,
    event_date: str,
    event_time: str,
    fulfilment_type: str,
    notes: str | None,
    discount_cents: int = 0,
    delivery_fee_cents: int = 0,
    items: list[dict] | None = None,
) -> int:
    items = items or []
    if fulfilment_type not in ("pickup", "delivery"):
        raise ValueError("fulfilment_type muss 'pickup' oder 'delivery' sein.")
    if not items:
        raise ValueError("Es muss mindestens eine Position geben.")

    notes = (notes or "").strip() or None

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO orders (
              customer_id, event_date, event_time, fulfilment_type, notes,
              discount_cents, delivery_fee_cents
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (customer_id, event_date, event_time, fulfilment_type, notes, int(discount_cents), int(delivery_fee_cents)),
        )
        order_id = int(cur.lastrowid)

        conn.executemany(
            """
            INSERT INTO order_items (
              order_id, product_id, description, quantity, unit, unit_price_cents, vat_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    order_id,
                    int(it["product_id"]) if it.get("product_id") else None,
                    it["description"].strip(),
                    float(it.get("quantity", 1) or 1),
                    (it.get("unit") or "Stk").strip() or "Stk",
                    int(it["unit_price_cents"]),
                    float(it.get("vat_rate", 0.19)),
                )
                for it in items
                if it.get("description", "").strip()
            ],
        )
        return order_id
    
def delete_order(order_id: int) -> None:
    """Löscht eine Bestellung vollständig (inkl. Positionen via ON DELETE CASCADE)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM orders WHERE id = ?", (int(order_id),))



# ------------------------------------------------------------
# Listen / Details
# ------------------------------------------------------------    
def list_orders_for_period(start_date: str, end_date: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              o.*,
              c.name AS customer_name, c.phone AS customer_phone, c.address AS customer_address
            FROM orders o
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE o.event_date BETWEEN ? AND ?
            ORDER BY o.event_date ASC, o.event_time ASC, o.id ASC
            """,
            (start_date, end_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_order_with_customer(order_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT o.*,
                   c.name AS customer_name, c.phone AS customer_phone, c.address AS customer_address
            FROM orders o
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE o.id = ?
            """,
            (order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Bestellung nicht gefunden.")
        return dict(row)


def get_order_items(order_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, product_id, description, quantity, unit, unit_price_cents, vat_rate
            FROM order_items
            WHERE order_id = ?
            ORDER BY id ASC
            """,
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------
# Status / Zahlung
# ------------------------------------------------------------
def update_status(order_id: int, new_status: str) -> None:
    allowed = {"open", "paid"}
    if new_status not in allowed:
        raise ValueError(f"Status muss einer von {sorted(allowed)} sein.")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE orders
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (new_status, int(order_id)),
        )


def set_payment_method(order_id: int, payment_method: str | None) -> None:
    """Speichert die Zahlungsart (Bar/Karte/...) in der Bestellung."""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE orders
            SET payment_method = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            ((payment_method or None), int(order_id)),
        )



# ------------------------------------------------------------
# Rechnung: Nummer vergeben (sequentiell)
# ------------------------------------------------------------
def assign_invoice_number(order_id: int) -> str:
    today = date.today().isoformat()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='next_invoice_number'"
        ).fetchone()

        if not row:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES ('next_invoice_number','1001')"
            )
            next_no = 1001
        else:
            next_no = int(row["value"])

        invoice_number = str(next_no)

        # Nur vergeben, wenn noch keine Rechnungsnummer gesetzt ist
        conn.execute(
            """
            UPDATE orders
            SET invoice_number = ?, invoice_date = ?, updated_at = datetime('now')
            WHERE id = ? AND invoice_number IS NULL
            """,
            (invoice_number, today, int(order_id)),
        )

        # Nummer hochzählen
        conn.execute(
            "UPDATE settings SET value = ? WHERE key='next_invoice_number'",
            (str(next_no + 1),),
        )

    return invoice_number


# ------------------------------------------------------------
# Summenberechnung (Brutto-Speicherung -> Netto/MwSt berechnen)
# Hinweis: Rabatt/Lieferpauschale werden vereinfacht dem höchsten MwSt-Satz zugeordnet.
# Wenn du "buchhalterisch exakt" willst: Rabatt proportional auf Steuersätze verteilen.
# ------------------------------------------------------------
def compute_totals(order_id: int) -> dict:
    with get_conn() as conn:
        o = conn.execute(
            "SELECT discount_cents, delivery_fee_cents FROM orders WHERE id = ?",
            (int(order_id),),
        ).fetchone()
        if not o:
            raise ValueError("Bestellung nicht gefunden.")

    items = get_order_items(order_id)

    by_vat: dict[float, dict] = {}
    for it in items:
        vat = float(it["vat_rate"])
        line_gross = int(round(float(it["quantity"]) * int(it["unit_price_cents"])))

        line_net = int(round(line_gross / (1.0 + vat)))
        line_vat = line_gross - line_net

        bucket = by_vat.setdefault(vat, {"gross": 0, "net": 0, "vat": 0})
        bucket["gross"] += line_gross
        bucket["net"] += line_net
        bucket["vat"] += line_vat

    discount = int(o["discount_cents"])
    delivery_fee = int(o["delivery_fee_cents"])

    if by_vat:
        vat_target = max(by_vat.keys())

        # Lieferung addieren
        add_net = int(round(delivery_fee / (1.0 + vat_target)))
        add_vat = delivery_fee - add_net
        by_vat[vat_target]["gross"] += delivery_fee
        by_vat[vat_target]["net"] += add_net
        by_vat[vat_target]["vat"] += add_vat

        # Rabatt abziehen
        sub_net = int(round(discount / (1.0 + vat_target)))
        sub_vat = discount - sub_net
        by_vat[vat_target]["gross"] -= discount
        by_vat[vat_target]["net"] -= sub_net
        by_vat[vat_target]["vat"] -= sub_vat

    net_total = sum(v["net"] for v in by_vat.values())
    vat_total = sum(v["vat"] for v in by_vat.values())
    gross_total = sum(v["gross"] for v in by_vat.values())

    return {
        "by_vat": by_vat,
        "net_total_cents": net_total,
        "vat_total_cents": vat_total,
        "gross_total_cents": gross_total,
        "discount_cents": discount,
        "delivery_fee_cents": delivery_fee,
    }
