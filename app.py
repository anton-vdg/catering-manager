import sqlite3
from datetime import date
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from io import BytesIO
from xml.sax.saxutils import escape

from flask import abort, send_file
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Projektordner: Von hier aus finden wir Datenbank und Dateien zuverlässig.
BASE_DIR = Path(__file__).parent

def init_db():
    """Legt fehlende Tabellen an und spielt die Startdaten ein."""
    db = sqlite3.connect(BASE_DIR / "products.db")
    db.execute("PRAGMA foreign_keys = ON")

    # 1. Kategorien sicherstellen – muss VOR category_id existieren.
    db.execute("""
        CREATE TABLE IF NOT EXISTS categories (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)

    # 2. Alte products-Tabelle um fehlende Spalten ergänzen.
    spalten = [z[1] for z in db.execute("PRAGMA table_info(products)")]
    if spalten:  # Tabelle existiert schon
        if "active" not in spalten:
            db.execute("ALTER TABLE products ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        if "category_id" not in spalten:
            db.execute("ALTER TABLE products ADD COLUMN category_id INTEGER REFERENCES categories(id)")
        if "tax_rate" not in spalten:
            db.execute("ALTER TABLE products ADD COLUMN tax_rate INTEGER NOT NULL DEFAULT 19")

    # 3. Struktur + Preisliste einspielen. Mehrfach ausführbar.
    db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
    db.executescript((BASE_DIR / "produktliste.sql").read_text(encoding="utf-8"))

    db.commit()
    db.close()


init_db()

# Die zentrale Flask-Anwendung / der lokale Webserver.
app = Flask(__name__)
FONT_DIR = BASE_DIR / "fonts"
pdfmetrics.registerFont(TTFont("ComicSans", str(FONT_DIR / "Comic Sans MS.ttf")))
pdfmetrics.registerFont(TTFont("ComicSans-Bold", str(FONT_DIR / "Comic Sans MS Bold.ttf")))
# Damit <b>...</b> in Paragraphen die fette Variante nimmt.
pdfmetrics.registerFontFamily(
    "ComicSans",
    normal="ComicSans", bold="ComicSans-Bold",
    italic="ComicSans", boldItalic="ComicSans-Bold",
)


def get_products(category_id=None):
    """Liest sichtbare Produkte, optional nur die einer Kategorie."""
    connection = sqlite3.connect(BASE_DIR / "products.db")
    connection.row_factory = sqlite3.Row

    sql = """
        SELECT p.id, p.name, p.price_cents, p.unit, p.tax_rate,
               COALESCE(c.name, 'Ohne Kategorie') AS category_name,
               COALESCE(c.sort_order, 9999)       AS category_sort
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.active = 1
    """
    params = []

    # Nur wenn eine Kategorie gewählt wurde, kommt der Zusatz dazu.
    if category_id is not None:
        sql += " AND p.category_id = ?"
        params.append(category_id)

    sql += " ORDER BY COALESCE(c.sort_order, 9999), p.name"

    products = connection.execute(sql, params).fetchall()
    connection.close()
    return products


def search_products(search_term):
    connection = sqlite3.connect(BASE_DIR / "products.db")
    connection.row_factory = sqlite3.Row

    products = connection.execute(
        """
        SELECT id, name, price_cents, unit, tax_rate
        FROM products
        WHERE active = 1 AND name LIKE ?
        ORDER BY name
        """,
        (f"%{search_term}%",),
    ).fetchall()

    connection.close()
    return products


def get_orders_for_day(selected_date):
    """Liest alle Aufträge und Positionen für ein bestimmtes Datum."""
    connection = sqlite3.connect(BASE_DIR / "products.db")
    connection.row_factory = sqlite3.Row

    # Uhrzeiten im Format HH:MM lassen sich als Text korrekt sortieren.
    order_rows = connection.execute(
        "SELECT * FROM orders WHERE order_date = ? ORDER BY order_time", (selected_date,)
    ).fetchall()

    orders = []
    for order_row in order_rows:
        order = dict(order_row)
        # JOIN ergänzt jede Bestellposition mit Produktname und Einheit.
        item_rows = connection.execute(
            """
            SELECT products.name, products.unit, order_items.quantity, order_items.unit_price_cents
            FROM order_items
            JOIN products ON products.id = order_items.product_id
            WHERE order_items.order_id = ?
            """,
            (order["id"],),
        ).fetchall()
        order["items"] = [dict(item) for item in item_rows]
        order["total_cents"] = sum(
            item["quantity"] * item["unit_price_cents"] for item in item_rows
        )
        orders.append(order)

    connection.close()
    return orders


@app.route("/")
def home():
    # Startseite aus dem Ordner templates laden.
    return render_template("home.html")


@app.route("/style.css")
def stylesheet():
    return send_from_directory(BASE_DIR, "style.css")


@app.route("/produkte")
def products():
    # Auswahl aus der URL lesen: /produkte?kategorie=5
    # Leer oder Unsinn -> None -> alle Kategorien anzeigen.
    kategorie = request.args.get("kategorie", "").strip()
    selected_category = int(kategorie) if kategorie.isdigit() else None

    rows = get_products(selected_category)

    # Flache Liste in Gruppen umbauen. Ist eine Kategorie gefiltert,
    # entsteht hier eben nur eine einzige Gruppe.
    gruppen = []
    for row in rows:
        if not gruppen or gruppen[-1]["name"] != row["category_name"]:
            gruppen.append({"name": row["category_name"], "produkte": []})
        gruppen[-1]["produkte"].append(dict(row))

    connection = sqlite3.connect(BASE_DIR / "products.db")
    connection.row_factory = sqlite3.Row
    categories = connection.execute(
        "SELECT id, name FROM categories ORDER BY sort_order, name"
    ).fetchall()
    connection.close()

    return render_template(
        "produkte.html",
        gruppen=gruppen,
        categories=categories,
        selected_category=selected_category,
        hinweis=request.args.get("hinweis"),
        fehler=request.args.get("fehler"),
    )

@app.route("/produkte/hinzufuegen", methods=["POST"])
def produkt_hinzufuegen():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip() or "Stück"
    preis_text = request.form.get("price", "").strip().replace(",", ".")
    zurueck = request.form.get("kategorie", "").strip()   # NEU

    category_id = request.form.get("category_id") or None
    if category_id is not None:
        category_id = int(category_id)

    # Hilfsfunktion: baut die Rücksprung-URL mit oder ohne Kategorie.
    def zurueck_url(**kwargs):
        if zurueck:
            kwargs["kategorie"] = zurueck
        return redirect(url_for("products", **kwargs))

    if not name:
        return zurueck_url(fehler="Bitte einen Namen eingeben.")

    try:
        price_cents = round(float(preis_text) * 100)
    except ValueError:
        return zurueck_url(fehler="Bitte einen gültigen Preis eingeben, z. B. 4,50.")

    if price_cents < 0:
        return zurueck_url(fehler="Der Preis darf nicht negativ sein.")

    connection = sqlite3.connect(BASE_DIR / "products.db")
    schon_da = connection.execute(
        "SELECT id FROM products WHERE active = 1 AND lower(name) = lower(?)", (name,)
    ).fetchone()
    if schon_da:
        connection.close()
        return zurueck_url(fehler=f"„{name}“ gibt es schon.")

    connection.execute(
        "INSERT INTO products (name, price_cents, unit, category_id) VALUES (?, ?, ?, ?)",
        (name, price_cents, unit, category_id),
    )
    connection.commit()
    connection.close()

    return zurueck_url(hinweis=f"„{name}“ wurde hinzugefügt.")


@app.route("/produkte/<int:product_id>/loeschen", methods=["POST"])
def produkt_loeschen(product_id):
    zurueck = request.form.get("kategorie", "").strip()   # NEU

    def zurueck_url(**kwargs):
        if zurueck:
            kwargs["kategorie"] = zurueck
        return redirect(url_for("products", **kwargs))

    connection = sqlite3.connect(BASE_DIR / "products.db")
    row = connection.execute(
        "SELECT name FROM products WHERE id = ? AND active = 1", (product_id,)
    ).fetchone()
    if row is None:
        connection.close()
        return zurueck_url(fehler="Produkt nicht gefunden.")

    connection.execute("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
    connection.commit()
    connection.close()

    return zurueck_url(hinweis=f"„{row['name']}“ wurde gelöscht.")

@app.route("/produkte/<int:product_id>/bearbeiten", methods=["GET", "POST"])
def produkt_bearbeiten(product_id):
    """Zeigt ein vorausgefülltes Formular und speichert die Änderungen."""
    # 'kategorie' steckt beim Aufruf in der URL (?kategorie=5) und beim
    # Absenden im Hidden-Feld des Formulars. request.values liest beides.
    zurueck = request.values.get("kategorie", "").strip()

    def zurueck_url(**kwargs):
        """Baut den Rücksprung – mit Kategorie, wenn eine gewählt war."""
        if zurueck:
            kwargs["kategorie"] = zurueck
        return redirect(url_for("products", **kwargs))

    connection = sqlite3.connect(BASE_DIR / "products.db")
    connection.row_factory = sqlite3.Row

    product = connection.execute(
        "SELECT id, name, price_cents, unit, tax_rate, category_id "
        "FROM products WHERE id = ? AND active = 1",
        (product_id,),
    ).fetchone()

    if product is None:
        connection.close()
        return zurueck_url(fehler="Produkt nicht gefunden.")

    categories = connection.execute(
        "SELECT id, name FROM categories ORDER BY sort_order, name"
    ).fetchall()

    def zeige_formular(werte, fehler_text=None):
        """Rendert die Seite. 'werte' sind die anzuzeigenden Feldinhalte."""
        connection.close()
        return render_template(
            "product_edit.html",
            product=werte,
            categories=categories,
            selected_category=zurueck,
            fehler=fehler_text,
        )

    # --- GET: nur das Formular zeigen ---
    if request.method == "GET":
        werte = dict(product)
        # Preis als Text "4,50" für das Eingabefeld vorbereiten.
        werte["price_text"] = f"{product['price_cents'] / 100:.2f}".replace(".", ",")
        return zeige_formular(werte)

    # --- POST: Änderungen speichern ---
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip() or "Stück"
    preis_text = request.form.get("price", "").strip().replace(",", ".")
    tax_text = request.form.get("tax_rate", "").strip()
    category_id = request.form.get("category_id") or None

    # Die eingegebenen Werte – damit das Formular bei Fehlern nicht leer ist.
    werte = {
        "id": product_id,
        "name": name,
        "unit": unit,
        "price_text": preis_text.replace(".", ","),
        "tax_rate": tax_text,
        "category_id": int(category_id) if category_id else None,
    }

    if not name:
        return zeige_formular(werte, "Bitte einen Namen eingeben.")

    try:
        price_cents = round(float(preis_text) * 100)
    except ValueError:
        return zeige_formular(werte, "Bitte einen gültigen Preis eingeben, z. B. 4,50.")

    if price_cents < 0:
        return zeige_formular(werte, "Der Preis darf nicht negativ sein.")

    if tax_text not in ("7", "19"):
        return zeige_formular(werte, "Bitte einen Steuersatz wählen.")

    # Anderes Produkt mit demselben Namen? (das eigene ausnehmen: id != ?)
    doppelt = connection.execute(
        "SELECT id FROM products "
        "WHERE active = 1 AND lower(name) = lower(?) AND id != ?",
        (name, product_id),
    ).fetchone()
    if doppelt:
        return zeige_formular(werte, f"„{name}“ gibt es schon.")

    connection.execute(
        """
        UPDATE products
        SET name = ?, price_cents = ?, unit = ?, tax_rate = ?, category_id = ?
        WHERE id = ?
        """,
        (name, price_cents, unit, int(tax_text), werte["category_id"], product_id),
    )
    connection.commit()
    connection.close()

    return zurueck_url(hinweis=f"„{name}“ wurde gespeichert.")

@app.route("/api/products")
def product_api():
    search_term = request.args.get("query", "").strip()
    if not search_term:
        return jsonify([])

    products = search_products(search_term)
    return jsonify([
        {
            "id": product["id"],
            "name": product["name"],
            "price_cents": product["price_cents"],
            "unit": product["unit"],
            "tax_rate": product["tax_rate"],
        }
        for product in products
    ])


@app.route("/api/orders", methods=["POST"])
def order_api():
    """Speichert eine Bestellung und ihre Positionen in einer Transaktion."""
    data = request.get_json(silent=True) or {}
    customer_name = data.get("customer_name", "").strip()
    delivery_address = data.get("delivery_address", "").strip()
    customer_phone = data.get("customer_phone", "").strip()
    order_date = data.get("order_date", "").strip()
    order_time = data.get("order_time", "").strip()
    fulfillment_type = data.get("fulfillment_type", "").strip()
    items = data.get("items", [])

    # Auch der Server prüft alle Pflichtdaten, nicht nur das HTML-Formular.
    if not customer_name or not customer_phone or not order_date or not order_time or not items:
        return jsonify({"error": "Bitte alle Pflichtfelder und mindestens ein Produkt angeben."}), 400
    if fulfillment_type not in {"abholung", "lieferung"}:
        return jsonify({"error": "Ungültige Art der Bestellung."}), 400

    try:
        with sqlite3.connect(BASE_DIR / "products.db") as connection:
            # Fremdschlüssel verhindern Verweise auf nicht vorhandene Produkte.
            connection.execute("PRAGMA foreign_keys = ON")

            # Zuerst den Auftrag speichern und seine neue ID merken.
            cursor = connection.execute(
                """
                INSERT INTO orders
                    (customer_name, delivery_address, customer_phone, order_date, order_time, fulfillment_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (customer_name, delivery_address, customer_phone, order_date, order_time, fulfillment_type),
            )
            order_id = cursor.lastrowid

            for item in items:
                product_id = int(item["product_id"])
                quantity = int(item["quantity"])
                if quantity < 1:
                    raise ValueError("Die Menge muss mindestens 1 sein.")

                product = connection.execute(
                    "SELECT price_cents FROM products WHERE id = ?", (product_id,)
                ).fetchone()
                if product is None:
                    raise ValueError("Ein ausgewähltes Produkt existiert nicht mehr.")

                connection.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, quantity, unit_price_cents)
                    VALUES (?, ?, ?, ?)
                    """,
                    (order_id, product_id, quantity, product[0]),
                )
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Ungültige Produktdaten."}), 400

    return jsonify({"message": "Bestellung gespeichert.", "order_id": order_id}), 201


@app.route("/tagesansicht")
def day_view():
    # Datum aus der URL lesen; ohne Angabe ist es der heutige Tag.
    selected_date = request.args.get("date", date.today().isoformat())
    try:
        date.fromisoformat(selected_date)
    except ValueError:
        selected_date = date.today().isoformat()

    return render_template(
        "tagesansicht.html",
        selected_date=selected_date,
        orders=get_orders_for_day(selected_date),
    )


@app.route("/bestellungen/<int:order_id>/loeschen", methods=["POST"])
def delete_order(order_id):
    """Löscht einen Auftrag und alle zugehörigen Positionen."""
    selected_date = request.form.get("date", date.today().isoformat())

    with sqlite3.connect(BASE_DIR / "products.db") as connection:
        # Erst die untergeordneten Positionen löschen, dann den Auftrag selbst.
        connection.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        connection.execute("DELETE FROM orders WHERE id = ?", (order_id,))

    # Nach dem Löschen zurück zur selben Tagesansicht gehen.
    return redirect(url_for("day_view", date=selected_date))

def get_order_details(order_id):
    """Liest Auftrag, Positionen (mit Produktname) und Gesamtbetrag."""
    with sqlite3.connect(BASE_DIR / "products.db") as connection:
        connection.row_factory = sqlite3.Row

        order = connection.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if order is None:
            return None, [], 0

        items = connection.execute(
            """
            SELECT products.name AS product_name, products.unit,
                   order_items.quantity, order_items.unit_price_cents
            FROM order_items
            JOIN products ON products.id = order_items.product_id
            WHERE order_items.order_id = ?
            """,
            (order_id,),
        ).fetchall()

    total_cents = sum(i["quantity"] * i["unit_price_cents"] for i in items)
    return order, items, total_cents


WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag"]


@app.route("/bestellungen/<int:order_id>/pdf")
def order_pdf(order_id):
    """Erzeugt ein A5-PDF mit allen Daten einer Bestellung."""
    order, items, _total_cents = get_order_details(order_id)
    if order is None:
        abort(404)

    day = date.fromisoformat(order["order_date"])
    date_text = f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.')}"
    fulfillment = "Abholung" if order["fulfillment_type"] == "abholung" else "Lieferung"

    base = ParagraphStyle("base", fontName="ComicSans", fontSize=14, leading=19)
    center = ParagraphStyle("center", parent=base, fontName="ComicSans-Bold",
                            fontSize=16, leading=20, alignment=TA_CENTER)
    right = ParagraphStyle("right", parent=base, fontName="ComicSans-Bold",
                           fontSize=16, leading=20, alignment=TA_RIGHT)
    heading = ParagraphStyle("heading", parent=base, fontName="ComicSans-Bold",
                             fontSize=12, leading=16, spaceBefore=14, spaceAfter=4)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A5,
        leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1 * cm, bottomMargin=1 * cm,
        title=f"Bestellung Nr. {order_id}",
    )

    # Kopfzeile: links leer, Mitte Tag und Datum, rechts Uhrzeit und Art.
    # Die beiden äußeren Spalten sind gleich breit, damit das Datum mittig sitzt.
    header = Table(
        [[
            "",
            Paragraph(escape(date_text), center),
            Paragraph(f"{escape(order['order_time'])} Uhr<br/>{fulfillment}", right),
        ]],
        colWidths=[3.9 * cm, 5 * cm, 3.9 * cm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))

    story = [header, Spacer(1, 0.5 * cm),
             Paragraph(f"<b>{escape(order['customer_name'])}</b>", base)]
    if order["delivery_address"]:
        story.append(Paragraph(escape(order["delivery_address"]), base))
    if order["customer_phone"]:
        story.append(Paragraph(escape(order["customer_phone"]), base))

    story.append(Paragraph("Bestellung", heading))
    for item in items:
        story.append(Paragraph(
            f"{item['quantity']} × {escape(item['product_name'])} ({escape(item['unit'])})",
            base,
        ))

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf",
                     download_name=f"Bestellung_{order_id}.pdf")



@app.route("/order.js")
def order_script():
    # JavaScript-Datei für die interaktive Bestellung ausliefern.
    return send_from_directory(BASE_DIR, "order.js")


# if __name__ == "__main__":
#     # Für Geräte im selben WLAN erreichbar; Debug aus Sicherheitsgründen aus.
#     app.run(host="0.0.0.0", port=5001, debug=False)

if __name__ == "__main__":
    app.run(debug=True)
