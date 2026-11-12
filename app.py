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


def get_products():
    """Liest alle Produkte aus der SQLite-Datenbank."""
    # Verbindung zur Datenbank öffnen.
    connection = sqlite3.connect(BASE_DIR / "products.db")
    # Zeilen per Spaltennamen lesbar machen, z. B. product["name"].
    connection.row_factory = sqlite3.Row

    products = connection.execute(
        "SELECT id, name, price_cents, unit FROM products ORDER BY name"
    ).fetchall()

    connection.close()
    return products


def search_products(search_term):
    """Sucht Produkte, deren Name den Suchbegriff enthält."""
    connection = sqlite3.connect(BASE_DIR / "products.db")
    connection.row_factory = sqlite3.Row

    # Das ? ist ein sicherer Platzhalter für den Suchbegriff.
    products = connection.execute(
        """
        SELECT id, name, price_cents, unit
        FROM products
        WHERE name LIKE ?
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
    return render_template("produkte.html", products=get_products())


@app.route("/api/products")
def product_api():
    # Den Wert aus /api/products?query=... auslesen.
    search_term = request.args.get("query", "").strip()
    if not search_term:
        return jsonify([])

    # SQL-Treffer als JSON an JavaScript im Browser zurückgeben.
    products = search_products(search_term)
    return jsonify(
        [
            {
                "id": product["id"],
                "name": product["name"],
                "price_cents": product["price_cents"],
                "unit": product["unit"],
            }
            for product in products
        ]
    )


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
