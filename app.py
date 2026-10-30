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

# Projektordner: Von hier aus finden wir Datenbank und Dateien zuverlässig.
BASE_DIR = Path(__file__).parent
# Die zentrale Flask-Anwendung / der lokale Webserver.
app = Flask(__name__)


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
    order_date = data.get("order_date", "").strip()
    order_time = data.get("order_time", "").strip()
    fulfillment_type = data.get("fulfillment_type", "").strip()
    items = data.get("items", [])

    # Auch der Server prüft alle Pflichtdaten, nicht nur das HTML-Formular.
    if not customer_name or not order_date or not order_time or not items:
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
                    (customer_name, delivery_address, order_date, order_time, fulfillment_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (customer_name, delivery_address, order_date, order_time, fulfillment_type),
            )
            order_id = cursor.lastrowid

            for item in items:
                product_id = int(item["product_id"])
                quantity = int(item["quantity"])
                if quantity < 1:
                    raise ValueError("Die Menge muss mindestens 1 sein.")

                # Preis neu aus der Datenbank lesen: Browser-Werte sind nie vertrauenswürdig.
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


@app.route("/order.js")
def order_script():
    # JavaScript-Datei für die interaktive Bestellung ausliefern.
    return send_from_directory(BASE_DIR, "order.js")


if __name__ == "__main__":
    # Für Geräte im selben WLAN erreichbar; Debug aus Sicherheitsgründen aus.
    app.run(host="0.0.0.0", port=5001, debug=False)
