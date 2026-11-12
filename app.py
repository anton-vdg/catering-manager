"""
Catering Manager – Flask-Anwendung
==================================

Das ist der "Server" des Projekts. Er nimmt Anfragen vom Browser entgegen,
liest und schreibt in die SQLite-Datenbank `products.db` und füllt die
HTML-Vorlagen aus dem Ordner `templates/` mit Daten.

Starten:  python app.py   ->   http://127.0.0.1:5000
"""

# ===================================================================
# 1. Importe
# ===================================================================
# Standardbibliothek von Python – nichts zu installieren.
import sqlite3                      # Datenbankzugriff
from datetime import date           # heutiges Datum für die Tagesansicht
from io import BytesIO              # PDF im Arbeitsspeicher statt auf Platte
from pathlib import Path            # Dateipfade unabhängig vom Betriebssystem
from xml.sax.saxutils import escape # Sonderzeichen (<, >, &) für PDFs entschärfen
from datetime import date, timedelta

# Flask = das Web-Framework. Ohne Flask gäbe es keine Routen und keine Templates.
from flask import (
    Flask,              # die Anwendung selbst
    abort,              # eine Anfrage mit Fehlercode abbrechen (z. B. 404)
    jsonify,            # Python-Daten als JSON an den Browser schicken
    redirect,           # Browser auf eine andere URL schicken
    render_template,    # HTML-Vorlage mit Daten füllen
    request,            # alles, was der Browser geschickt hat (Formular, URL, JSON)
    send_file,          # eine Datei (hier: PDF) ausliefern
    send_from_directory,# eine Datei aus dem Projektordner ausliefern (CSS, JS)
    url_for,            # URL aus dem Namen einer Route bauen
)

# ReportLab erzeugt die PDFs. Wird nur von order_pdf() gebraucht.
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


# ===================================================================
# 2. Pfade
# ===================================================================
# BASE_DIR = der Ordner, in dem diese Datei liegt. Von hier aus werden
# Datenbank, CSS, JS und SQL-Dateien gefunden – egal, von wo die App startet.
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "products.db"


# ===================================================================
# 3. Datenbank
# ===================================================================
def connect_db():
    """
    Öffnet die Datenbank und gibt die Verbindung zurück.

    Wird von JEDER Funktion benutzt, die mit der Datenbank spricht.
    Die zwei Einstellungen darin sind der eigentliche Grund für diese Funktion:

    - row_factory = sqlite3.Row
      Danach liest man Zeilen per Spaltenname: produkt["name"] statt produkt[1].
      Ohne das müsste man sich merken, an welcher Position welche Spalte steht.

    - PRAGMA foreign_keys = ON
      SQLite prüft Fremdschlüssel standardmäßig NICHT. Ohne diese Zeile könnte
      man eine Bestellzeile auf ein gelöschtes Produkt verweisen lassen.
      Das PRAGMA gilt pro Verbindung, muss also bei jeder neu gesetzt werden.
    """
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    """
    Wird EINMAL beim Start der App aufgerufen (siehe Dateiende).

    Aufgabe: eine bereits vorhandene, ältere Datenbank auf den aktuellen Stand
    bringen und die Preisliste einspielen. Mehrfaches Ausführen ist unschädlich,
    weil alles mit "IF NOT EXISTS" bzw. "INSERT OR IGNORE" arbeitet.
    """
    db = connect_db()

    # 3a) Kategorietabelle anlegen, falls sie fehlt.
    #     Muss VOR der category_id-Spalte passieren, weil products darauf verweist.
    db.execute("""
        CREATE TABLE IF NOT EXISTS categories (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)

    # 3b) Existiert die products-Tabelle schon, ergänze fehlende Spalten.
    #     PRAGMA table_info liefert eine Zeile pro Spalte; [1] ist der Name.
    spalten = [zeile[1] for zeile in db.execute("PRAGMA table_info(products)")]
    if spalten:
        if "active" not in spalten:
            db.execute("ALTER TABLE products ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        if "category_id" not in spalten:
            db.execute(
                "ALTER TABLE products ADD COLUMN category_id INTEGER "
                "REFERENCES categories(id)"
            )
        if "tax_rate" not in spalten:
            db.execute(
                "ALTER TABLE products ADD COLUMN tax_rate INTEGER NOT NULL DEFAULT 19"
            )

    # 3c) schema.sql = Tabellenstruktur, produktliste.sql = Startinhalte.
    #     executescript führt mehrere SQL-Befehle hintereinander aus.
    db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
    db.executescript((BASE_DIR / "produktliste.sql").read_text(encoding="utf-8"))

    db.commit()
    db.close()


# ===================================================================
# 4. Flask-Anwendung und PDF-Schriften
# ===================================================================
app = Flask(__name__)

FONT_DIR = BASE_DIR / "fonts"
pdfmetrics.registerFont(TTFont("ComicSans", str(FONT_DIR / "Comic Sans MS.ttf")))
pdfmetrics.registerFont(TTFont("ComicSans-Bold", str(FONT_DIR / "Comic Sans MS Bold.ttf")))
# Damit <b>...</b> in einem Paragraph die fette Variante benutzt.
pdfmetrics.registerFontFamily(
    "ComicSans",
    normal="ComicSans",
    bold="ComicSans-Bold",
    italic="ComicSans",
    boldItalic="ComicSans-Bold",
)


def euro(cents):
    """
    12345 -> '123,45 €'.

    Benutzt in: order_pdf() für den Gesamtbetrag.
    Die HTML-Vorlagen formatieren selbst über den Jinja-Filter '%.2f'|format().
    """
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


# ===================================================================
# 5. Lesefunktionen (werden von den Routen weiter unten aufgerufen)
# ===================================================================
def get_products(category_id=None):
    """
    Liest alle SICHTBAREN Produkte, optional nur die einer Kategorie.

    category_id=None  -> alle Kategorien (Produkteseite ohne Filter)
    category_id=5     -> nur Produkte der Kategorie 5

    Verwendet in: products()

    Das COALESCE(...) sorgt dafür, dass Produkte ohne Kategorie nicht
    verschwinden, sondern als "Ohne Kategorie" auftauchen.
    Das ? ist ein Platzhalter – der Wert wird sicher eingesetzt,
    damit niemand SQL über das Suchfeld einschleusen kann.
    """
    connection = connect_db()

    sql = """
        SELECT p.id, p.name, p.price_cents, p.unit, p.tax_rate,
               COALESCE(c.name, 'Ohne Kategorie') AS category_name,
               COALESCE(c.sort_order, 9999)       AS category_sort
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.active = 1
    """
    params = []

    # Der Filter wird nur angehängt, wenn wirklich eine Kategorie gewählt ist.
    if category_id is not None:
        sql += " AND p.category_id = ?"
        params.append(category_id)

    sql += " ORDER BY COALESCE(c.sort_order, 9999), p.name"

    products = connection.execute(sql, params).fetchall()
    connection.close()
    return products


def search_products(search_term):
    """
    Sucht sichtbare Produkte, deren Name den Suchbegriff enthält.

    Verwendet in: product_api()  ->  aufgerufen von order.js beim Tippen.

    LIKE '%begriff%' bedeutet "enthält". Die Prozentzeichen sind der
    Platzhalter dafür, das ? setzt den Suchbegriff sicher ein.
    """
    connection = connect_db()

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
    """
    Liest alle Bestellungen eines Tages samt Positionen und Gesamtsumme.

    selected_date ist ein Text im Format "2026-11-12", weil SQLite
    Datumswerte als Text speichert. Dieses Format lässt sich alphabetisch
    sortieren – deshalb funktioniert ORDER BY order_time.

    Verwendet in: day_view()

    Hinweis: Pro Bestellung wird eine eigene Abfrage gemacht. Bei 20
    Bestellungen am Tag sind das 20 Abfragen – für diesen Betrieb völlig okay.
    """
    connection = connect_db()

    order_rows = connection.execute(
        "SELECT * FROM orders WHERE order_date = ? ORDER BY order_time",
        (selected_date,),
    ).fetchall()

    orders = []
    for order_row in order_rows:
        order = dict(order_row)

        # JOIN holt zu jeder Position den Produktnamen und die Einheit dazu.
        item_rows = connection.execute(
            """
            SELECT products.name, products.unit,
                   order_items.quantity, order_items.unit_price_cents
            FROM order_items
            JOIN products ON products.id = order_items.product_id
            WHERE order_items.order_id = ?
            """,
            (order["id"],),
        ).fetchall()

        order["items"] = [dict(item) for item in item_rows]
        # Gesamtbetrag = Menge × damals gespeicherter Preis, aufsummiert.
        order["total_cents"] = sum(
            item["quantity"] * item["unit_price_cents"] for item in item_rows
        )
        orders.append(order)

    connection.close()
    return orders


def get_order_details(order_id):
    """
    Liest eine einzelne Bestellung samt Positionen und Gesamtsumme.

    Verwendet in: order_pdf()
    Gibt (order, items, total_cents) zurück. Ist die Bestellung nicht
    vorhanden, kommt (None, [], 0) zurück – der Aufrufer prüft das.
    """
    connection = connect_db()

    order = connection.execute(
        "SELECT * FROM orders WHERE id = ?", (order_id,)
    ).fetchone()

    if order is None:
        connection.close()
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

    connection.close()

    total_cents = sum(item["quantity"] * item["unit_price_cents"] for item in items)
    return order, items, total_cents

def week_range(datum):
    """
    Gibt (Montag, Sonntag) der Woche zurück, in der `datum` liegt.

    date.weekday() liefert 0 für Montag, 6 für Sonntag.
    Ein Datum minus seinen weekday-Wert landet immer auf Montag.
    Beispiel: Mittwoch, 12.11.2026 -> weekday()=2
              12.11. - 2 Tage = 10.11. = Montag
    """
    montag = datum - timedelta(days=datum.weekday())
    sonntag = montag + timedelta(days=6)
    return montag, sonntag


def get_week_summary(montag, sonntag):
    """
    Summiert alle Positionen einer Woche pro Produkt.

    montag/sonntag sind ISO-Text wie "2026-11-10", damit BETWEEN
    auf dem Textvergleich funktioniert (SQLite-Datumsspeicherung).

    Verwendet in: week_view()

    Wichtig: SUM(quantity) summiert NUR Positionen, die es in dieser
    Woche tatsächlich gab. Produkte, die niemand bestellt hat, tauchen
    nicht auf – das ist gewollt, sonst wäre die Liste riesig.
    """
    connection = connect_db()

    rows = connection.execute(
        """
        SELECT p.id, p.name, p.unit,
               COALESCE(c.name, 'Ohne Kategorie') AS category_name,
               COALESCE(c.sort_order, 9999)       AS category_sort,
               SUM(oi.quantity)                  AS total_quantity,
               SUM(oi.quantity * oi.unit_price_cents) AS total_cents
        FROM order_items oi
        JOIN orders   o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE o.order_date BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY COALESCE(c.sort_order, 9999), p.name
        """,
        (montag, sonntag),
    ).fetchall()

    # Zusatzinfo für die Kopfzeile.
    bestellungen = connection.execute(
        "SELECT COUNT(*) FROM orders WHERE order_date BETWEEN ? AND ?",
        (montag, sonntag),
    ).fetchone()[0]

    kunden = connection.execute(
        "SELECT COUNT(DISTINCT customer_name) FROM orders "
        "WHERE order_date BETWEEN ? AND ?",
        (montag, sonntag),
    ).fetchone()[0]

    connection.close()
    return rows, bestellungen, kunden


# ===================================================================
# 6. Routen: Seiten und statische Dateien
# ===================================================================
@app.route("/")
def home():
    """Startseite mit dem Formular für neue Bestellungen. Datei: home.html"""
    return render_template("home.html")


@app.route("/style.css")
def stylesheet():
    """
    Liefert das Stylesheet aus. Nötig, weil Flask Dateien im Projektordner
    nicht automatisch ausliefert – nur den Ordner "static/".
    Eingebunden in: allen HTML-Dateien über <link rel="stylesheet" href="/style.css">
    """
    return send_from_directory(BASE_DIR, "style.css")


@app.route("/order.js")
def order_script():
    """
    Liefert das JavaScript der Bestellseite aus.
    Eingebunden in: home.html über <script src="/order.js">
    """
    return send_from_directory(BASE_DIR, "order.js")

@app.route("/order_edit.js")
def order_edit_script():
    """
    Liefert das JavaScript der Bearbeiten-Seite aus.
    Eingebunden in: order_edit.html
    """
    return send_from_directory(BASE_DIR, "order_edit.js")


# ===================================================================
# 7. Routen: Produkte
# ===================================================================
@app.route("/produkte")
def products():
    """
    Produkteliste, optional nach Kategorie gefiltert. Datei: produkte.html

    Der Filter steckt in der URL:  /produkte?kategorie=5
    Kein Parameter -> alle Kategorien.
    """
    # isdigit() prüft, ob wirklich nur Ziffern drinstehen. Sonst None.
    # Das verhindert Abstürze, wenn jemand ?kategorie=abc in die URL tippt.
    kategorie = request.args.get("kategorie", "").strip()
    selected_category = int(kategorie) if kategorie.isdigit() else None

    rows = get_products(selected_category)

    # Aus der flachen Liste Gruppen bauen: pro Kategorie ein Eintrag.
    # Die Sortierung kommt schon aus dem SQL, deshalb reicht ein Vergleich
    # mit dem zuletzt angelegten Gruppennamen.
    gruppen = []
    for row in rows:
        if not gruppen or gruppen[-1]["name"] != row["category_name"]:
            gruppen.append({"name": row["category_name"], "produkte": []})
        gruppen[-1]["produkte"].append(dict(row))

    connection = connect_db()
    categories = connection.execute(
        "SELECT id, name FROM categories ORDER BY sort_order, name"
    ).fetchall()
    connection.close()

    return render_template(
        "produkte.html",
        gruppen=gruppen,
        categories=categories,
        selected_category=selected_category,
        # hinweis/fehler kommen als ?hinweis=... aus der URL, gesetzt von
        # den Routen weiter unten nach einer erfolgreichen Aktion.
        hinweis=request.args.get("hinweis"),
        fehler=request.args.get("fehler"),
    )


@app.route("/produkte/hinzufuegen", methods=["POST"])
def produkt_hinzufuegen():
    """
    Legt ein neues Produkt an.
    Abgeschickt von: dem Formular in produkte.html.
    """
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip() or "Stück"
    preis_text = request.form.get("price", "").strip().replace(",", ".")
    tax_text = request.form.get("tax_rate", "7").strip()
    zurueck = request.form.get("kategorie", "").strip()

    # Leerer Wert im <select> kommt als "" an – daraus None machen.
    # int() kann auch scheitern, wenn jemand am HTML manipuliert hat.
    category_id = request.form.get("category_id") or None
    try:
        category_id = int(category_id) if category_id else None
    except ValueError:
        category_id = None

    def zurueck_url(**kwargs):
        """
        Baut die Rücksprung-URL. Die gewählte Kategorie wird mitgenommen,
        damit man nach dem Speichern wieder in derselben Ansicht landet.
        """
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

    if tax_text not in ("7", "19"):
        return zurueck_url(fehler="Bitte einen Steuersatz wählen.")

    connection = connect_db()

    # Doppelte Namen verhindern. lower() macht den Vergleich
    # unabhängig von Groß-/Kleinschreibung: "Ente" = "ente".
    schon_da = connection.execute(
        "SELECT id FROM products WHERE active = 1 AND lower(name) = lower(?)",
        (name,),
    ).fetchone()
    if schon_da:
        connection.close()
        return zurueck_url(fehler=f"„{name}“ gibt es schon.")

    connection.execute(
        """
        INSERT INTO products (name, price_cents, unit, tax_rate, category_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, price_cents, unit, int(tax_text), category_id),
    )
    connection.commit()
    connection.close()

    return zurueck_url(hinweis=f"„{name}“ wurde hinzugefügt.")


@app.route("/produkte/<int:product_id>/loeschen", methods=["POST"])
def produkt_loeschen(product_id):
    """
    "Löscht" ein Produkt, indem active auf 0 gesetzt wird.
    Abgeschickt von: dem 🗑️-Knopf in produkte.html.

    Warum kein echtes DELETE?
    Alte Bestellungen verweisen über order_items.product_id auf das Produkt.
    Ein DELETE würde diese Verweise zerstören – alte Rechnungen wären kaputt.
    Mit active = 0 verschwindet das Produkt nur aus der Auswahl.
    """
    zurueck = request.form.get("kategorie", "").strip()

    def zurueck_url(**kwargs):
        if zurueck:
            kwargs["kategorie"] = zurueck
        return redirect(url_for("products", **kwargs))

    connection = connect_db()
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
    """
    Zeigt ein vorausgefülltes Formular und speichert die Änderungen.
    Datei: product_edit.html
    Aufgerufen von: dem ✏️-Knopf in produkte.html.

    GET  = Formular anzeigen (Werte aus der Datenbank)
    POST = Änderungen speichern (Werte aus dem Formular)

    request.values liest BEIDES: URL-Parameter (?kategorie=5) und
    Formularfelder. Damit funktioniert derselbe Code für GET und POST.
    """
    zurueck = request.values.get("kategorie", "").strip()

    def zurueck_url(**kwargs):
        if zurueck:
            kwargs["kategorie"] = zurueck
        return redirect(url_for("products", **kwargs))

    connection = connect_db()

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
        """
        Rendert product_edit.html. 'werte' enthält die anzuzeigenden
        Feldinhalte – beim GET die gespeicherten, beim POST die gerade
        eingegebenen (damit bei einem Fehler nichts verloren geht).
        """
        connection.close()
        return render_template(
            "product_edit.html",
            product=werte,
            categories=categories,
            selected_category=zurueck,
            fehler=fehler_text,
        )

    # ---------- GET: nur anzeigen ----------
    if request.method == "GET":
        werte = dict(product)
        # Preis als "4,50" fürs Eingabefeld vorbereiten (deutsche Schreibweise).
        werte["price_text"] = f"{product['price_cents'] / 100:.2f}".replace(".", ",")
        return zeige_formular(werte)

    # ---------- POST: speichern ----------
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip() or "Stück"
    preis_text = request.form.get("price", "").strip().replace(",", ".")
    tax_text = request.form.get("tax_rate", "").strip()
    category_id = request.form.get("category_id") or None

    try:
        category_id = int(category_id) if category_id else None
    except ValueError:
        category_id = None

    # Die eingegebenen Werte für ein erneutes Anzeigen des Formulars.
    werte = {
        "id": product_id,
        "name": name,
        "unit": unit,
        "price_text": preis_text.replace(".", ","),
        "tax_rate": tax_text,
        "category_id": category_id,
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

    # Gibt es ein ANDERES Produkt mit demselben Namen?
    # id != ? nimmt das eigene Produkt aus, sonst würde es sich selbst blockieren.
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
        (name, price_cents, unit, int(tax_text), category_id, product_id),
    )
    connection.commit()
    connection.close()

    return zurueck_url(hinweis=f"„{name}“ wurde gespeichert.")


# ===================================================================
# 8. API für die Bestellseite
# ===================================================================
@app.route("/api/products")
def product_api():
    """
    Liefert Suchergebnisse als JSON an order.js.
    Aufgerufen von: order.js beim Tippen ins Suchfeld (fetch).
    Antwort z. B.: [{"id": 5, "name": "Ente", "price_cents": 4000, ...}]

    tax_rate MUSS mitgeliefert werden – ohne das Feld rechnet order.js
    die MwSt. nicht aus und zeigt NaN an.
    """
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
    """
    Speichert eine Bestellung samt Positionen.
    Aufgerufen von: order.js beim Absenden des Formulars (fetch, JSON body).

    Alles passiert in EINER Verbindung. Entweder wird der Auftrag mit allen
    Positionen gespeichert – oder bei einem Fehler gar nichts. Man nennt das
    eine Transaktion: kein halb gespeicherter Auftrag ohne Positionen.
    """
    data = request.get_json(silent=True) or {}
    customer_name = data.get("customer_name", "").strip()
    delivery_address = data.get("delivery_address", "").strip()
    customer_phone = data.get("customer_phone", "").strip()
    order_date = data.get("order_date", "").strip()
    order_time = data.get("order_time", "").strip()
    fulfillment_type = data.get("fulfillment_type", "").strip()
    items = data.get("items", [])

    # Der Server prüft selbst. HTML-Felder mit required reichen nicht,
    # weil man fetch auch ohne Browser aufrufen kann.
    if not customer_name or not customer_phone or not order_date \
            or not order_time or not items:
        return jsonify({
            "error": "Bitte alle Pflichtfelder und mindestens ein Produkt angeben."
        }), 400

    if fulfillment_type not in {"abholung", "lieferung"}:
        return jsonify({"error": "Ungültige Art der Bestellung."}), 400

    connection = connect_db()
    try:
        # 1) Den Auftrag speichern und seine neue ID merken.
        cursor = connection.execute(
            """
            INSERT INTO orders
                (customer_name, delivery_address, customer_phone,
                 order_date, order_time, fulfillment_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (customer_name, delivery_address, customer_phone,
             order_date, order_time, fulfillment_type),
        )
        order_id = cursor.lastrowid

        # 2) Die Positionen speichern.
        for item in items:
            product_id = int(item["product_id"])
            quantity = int(item["quantity"])
            if quantity < 1:
                raise ValueError("Die Menge muss mindestens 1 sein.")

            # Preis aus der DATENBANK lesen, nicht aus dem Browser.
            # Sonst könnte jemand den Preis manipulieren.
            product = connection.execute(
                "SELECT price_cents FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                raise ValueError("Ein ausgewähltes Produkt existiert nicht mehr.")

            # unit_price_cents ist ein SNAPSHOT: der Preis zum Bestellzeitpunkt.
            # Ändert sich der Produktpreis später, bleibt die Rechnung korrekt.
            connection.execute(
                """
                INSERT INTO order_items
                    (order_id, product_id, quantity, unit_price_cents)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, product_id, quantity, product["price_cents"]),
            )

        connection.commit()
    except (KeyError, TypeError, ValueError, sqlite3.IntegrityError):
        # rollback() macht alle Änderungen dieser Transaktion rückgängig.
        connection.rollback()
        connection.close()
        return jsonify({"error": "Ungültige Produktdaten."}), 400

    connection.close()
    return jsonify({"message": "Bestellung gespeichert.", "order_id": order_id}), 201


# ===================================================================
# 9. Tagesansicht
# ===================================================================
@app.route("/tagesansicht")
def day_view():
    """
    Alle Bestellungen eines Tages. Datei: tagesansicht.html
    Datum kommt aus der URL:  /tagesansicht?date=2026-11-12
    Ohne Angabe oder bei ungültigem Datum: heute.
    """
    selected_date = request.args.get("date", date.today().isoformat())

    try:
        date.fromisoformat(selected_date)
    except ValueError:
        selected_date = date.today().isoformat()

    # Für die Vor/Zurück-Links: der Tag davor und danach.
    # date.fromisoformat() ist oben schon geprüft, deshalb hier sicher.
    tag = date.fromisoformat(selected_date)

    return render_template(
        "tagesansicht.html",
        selected_date=selected_date,
        orders=get_orders_for_day(selected_date),
        hinweis=request.args.get("hinweis"),
        vorheriger_tag=(tag - timedelta(days=1)).isoformat(),
        naechster_tag=(tag + timedelta(days=1)).isoformat(),
    )


@app.route("/wochenansicht")
def week_view():
    """
    Aggregierte Mengen pro Produkt für eine Kalenderwoche.
    Datei: wochenansicht.html

    Datum aus der URL:  /wochenansicht?date=2026-11-12
    Daraus wird die Woche ermittelt (Montag..Sonntag), in der es liegt.
    Ohne Datum: aktuelle Woche.
    """
    datum_text = request.args.get("date", date.today().isoformat())

    try:
        datum = date.fromisoformat(datum_text)
    except ValueError:
        datum = date.today()

    montag, sonntag = week_range(datum)

    rows, bestellungen, kunden = get_week_summary(
        montag.isoformat(), sonntag.isoformat()
    )

    # Flache Liste wie auf der Produkteseite in Kategorien gruppieren.
    gruppen = []
    gesamt_cents = 0
    for row in rows:
        if not gruppen or gruppen[-1]["name"] != row["category_name"]:
            gruppen.append({"name": row["category_name"], "produkte": []})
        gruppen[-1]["produkte"].append(dict(row))
        gesamt_cents += row["total_cents"]

    # Vor/Zurück-Links im Template brauchen fertige URLs.
    vorherige = (montag - timedelta(days=7)).isoformat()
    naechste = (montag + timedelta(days=7)).isoformat()

    return render_template(
        "wochenansicht.html",
        selected_date=datum.isoformat(),
        montag=montag,
        sonntag=sonntag,
        kalenderwoche=montag.isocalendar()[1],
        gruppen=gruppen,
        bestellungen=bestellungen,
        kunden=kunden,
        gesamt_cents=gesamt_cents,
        vorherige=vorherige,
        naechste=naechste,
    )


@app.route("/bestellungen/<int:order_id>/loeschen", methods=["POST"])
def delete_order(order_id):
    """
    Löscht eine Bestellung samt Positionen.
    Abgeschickt von: dem 🗑️-Knopf in tagesansicht.html.

    Hier ist ein echtes DELETE richtig, weil Bestellungen keine
    "Geschichte" für andere Tabellen sind. Ohne die Reihenfolge
    (erst Positionen, dann Auftrag) würde der Fremdschlüssel meckern.
    """
    selected_date = request.form.get("date", date.today().isoformat())

    connection = connect_db()
    connection.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    connection.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    connection.commit()
    connection.close()

    # Zurück zur selben Tagesansicht, nicht zur Startseite.
    return redirect(url_for("day_view", date=selected_date))


@app.route("/bestellungen/<int:order_id>/bearbeiten", methods=["GET", "POST"])
def order_bearbeiten(order_id):
    """
    Bestellung bearbeiten: Stammdaten, Mengen, Positionen hinzufügen/entfernen.
    Datei: order_edit.html
    Aufgerufen von: dem ✏️-Knopf in tagesansicht.html.

    GET  = Formular mit den gespeicherten Werten zeigen
    POST = Änderungen speichern
    """
    connection = connect_db()

    order = connection.execute(
        "SELECT * FROM orders WHERE id = ?", (order_id,)
    ).fetchone()

    if order is None:
        connection.close()
        return redirect(url_for("day_view"))

    # Bestehende Positionen mit Produktnamen.
    items = connection.execute(
        """
        SELECT order_items.id, order_items.product_id, order_items.quantity,
               order_items.unit_price_cents,
               products.name, products.unit
        FROM order_items
        JOIN products ON products.id = order_items.product_id
        WHERE order_items.order_id = ?
        ORDER BY order_items.id
        """,
        (order_id,),
    ).fetchall()

    # Alle sichtbaren Produkte für das Auswahlfeld "Position hinzufügen".
    products = connection.execute(
        "SELECT id, name, price_cents, unit FROM products "
        "WHERE active = 1 ORDER BY name"
    ).fetchall()

    def zeige_formular(werte, positionen, fehler_text=None):
        """
        Rendert order_edit.html.
        werte      = anzuzeigende Stammdaten
        positionen = anzuzeigende Positionen
        Beim GET kommen beide aus der Datenbank, beim Fehlerfall aus dem
        Formular bzw. aus der unveränderten Datenbank.
        """
        connection.close()
        return render_template(
            "order_edit.html",
            order=werte,
            items=positionen,
            products=products,
            fehler=fehler_text,
        )

    # ---------- GET: nur anzeigen ----------
    if request.method == "GET":
        return zeige_formular(dict(order), [dict(i) for i in items])

    # ---------- POST: speichern ----------
    customer_name = request.form.get("customer_name", "").strip()
    customer_phone = request.form.get("customer_phone", "").strip()
    delivery_address = request.form.get("delivery_address", "").strip()
    order_date = request.form.get("order_date", "").strip()
    order_time = request.form.get("order_time", "").strip()
    fulfillment_type = request.form.get("fulfillment_type", "").strip()

    # Die eingegebenen Stammdaten – damit bei einem Fehler nichts verloren geht.
    neue_werte = {
        "id": order_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "delivery_address": delivery_address,
        "order_date": order_date,
        "order_time": order_time,
        "fulfillment_type": fulfillment_type,
    }

    # ---- Prüfungen VOR dem Schreiben ----
    if not customer_name or not customer_phone or not order_date or not order_time:
        return zeige_formular(neue_werte, [dict(i) for i in items],
                              "Bitte Name, Telefon, Datum und Uhrzeit ausfüllen.")

    if fulfillment_type not in {"abholung", "lieferung"}:
        return zeige_formular(neue_werte, [dict(i) for i in items],
                              "Bitte Abholung oder Lieferung wählen.")

    try:
        date.fromisoformat(order_date)
    except ValueError:
        return zeige_formular(neue_werte, [dict(i) for i in items],
                              "Ungültiges Datum.")

    # ---- Alles in einer Transaktion schreiben ----
    try:
        connection.execute(
            """
            UPDATE orders
            SET customer_name = ?, customer_phone = ?, delivery_address = ?,
                order_date = ?, order_time = ?, fulfillment_type = ?
            WHERE id = ?
            """,
            (customer_name, customer_phone, delivery_address,
             order_date, order_time, fulfillment_type, order_id),
        )

        # Bestehende Positionen: Menge ändern, 0 bedeutet "entfernen".
        # Das Feld heißt im HTML "menge_<id>" – z. B. menge_7.
        for item in items:
            roh = request.form.get(f"menge_{item['id']}", "").strip()

            # Feld geleert -> unverändert lassen (kein versehentliches Löschen).
            if not roh:
                continue

            try:
                menge = int(roh)
            except ValueError:
                continue

            if menge < 0:
                continue

            if menge == 0:
                connection.execute(
                    "DELETE FROM order_items WHERE id = ?", (item["id"],)
                )
            else:
                # WICHTIG: unit_price_cents bleibt unangetastet.
                # Der damals gespeicherte Preis gilt weiter, auch wenn sich
                # der Produktpreis inzwischen geändert hat.
                connection.execute(
                    "UPDATE order_items SET quantity = ? WHERE id = ?",
                    (menge, item["id"]),
                )

        # ---- Neue Positionen aus der Produktsuche ----
        # order_edit.js legt für jedes hinzugefügte Produkt ein Feld
        # "neu_menge_<produkt_id>" an. Wir suchen alle solche Felder.
        for feldname, wert in list(request.form.items()):
            if not feldname.startswith("neu_menge_"):
                continue

            # Aus "neu_menge_5" die 5 herausschneiden.
            try:
                produkt_id = int(feldname[len("neu_menge_"):])
                menge = int(wert)
            except ValueError:
                continue

            if menge < 1:
                continue

            produkt = connection.execute(
                "SELECT price_cents FROM products WHERE id = ? AND active = 1",
                (produkt_id,),
            ).fetchone()

            if produkt is None:
                continue

            # Ist das Produkt schon in dieser Bestellung?
            # Dann nur die Menge erhöhen und den DAMALIGEN Preis stehen lassen.
            vorhanden = connection.execute(
                "SELECT id FROM order_items WHERE order_id = ? AND product_id = ?",
                (order_id, produkt_id),
            ).fetchone()

            if vorhanden:
                connection.execute(
                    "UPDATE order_items SET quantity = quantity + ? WHERE id = ?",
                    (menge, vorhanden["id"]),
                )
            else:
                # Neue Position: hier gilt der HEUTIGE Preis als Snapshot.
                connection.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, quantity, unit_price_cents)
                    VALUES (?, ?, ?, ?)
                    """,
                    (order_id, produkt_id, menge, produkt["price_cents"]),
                )

        # Eine Bestellung ohne Positionen ergibt keinen Sinn.
        anzahl = connection.execute(
            "SELECT COUNT(*) FROM order_items WHERE order_id = ?", (order_id,)
        ).fetchone()[0]

        if anzahl == 0:
            raise ValueError("Eine Bestellung braucht mindestens eine Position.")

        connection.commit()

    except (ValueError, sqlite3.IntegrityError) as fehler:
        # rollback() macht alle Änderungen dieser Transaktion rückgängig –
        # kein halb gespeicherter Zustand.
        connection.rollback()

        # Positionen neu laden, weil die Änderungen gerade verworfen wurden.
        items = connection.execute(
            """
            SELECT order_items.id, order_items.product_id, order_items.quantity,
                   order_items.unit_price_cents,
                   products.name, products.unit
            FROM order_items
            JOIN products ON products.id = order_items.product_id
            WHERE order_items.order_id = ?
            ORDER BY order_items.id
            """,
            (order_id,),
        ).fetchall()

        return zeige_formular(neue_werte, [dict(i) for i in items], str(fehler))

    connection.close()

    # Zur Tagesansicht des (evtl. geänderten) Datums springen.
    return redirect(url_for(
        "day_view",
        date=order_date,
        hinweis=f"Bestellung Nr. {order_id} wurde gespeichert.",
    ))

# ===================================================================
# 10. PDF
# ===================================================================
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag"]


@app.route("/bestellungen/<int:order_id>/pdf")
def order_pdf(order_id):
    """
    Erzeugt ein A5-PDF einer Bestellung und schickt es an den Browser.
    Aufgerufen von: dem 📄-Knopf in tagesansicht.html (öffnet neuen Tab).

    Die Struktur ist immer gleich bei ReportLab:
      1. Styles definieren (Schriftart, Größe, Ausrichtung)
      2. buffer = BytesIO()  -> das PDF entsteht im Arbeitsspeicher
      3. doc = SimpleDocTemplate(...)  -> Seite mit Rändern
      4. story = Liste von Absätzen/Tabellen  -> der Inhalt
      5. doc.build(story)  -> schreibt ins buffer
      6. send_file(buffer) -> schickt es raus
    """
    order, items, total_cents = get_order_details(order_id)
    if order is None:
        abort(404)

    day = date.fromisoformat(order["order_date"])
    date_text = f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.')}"
    fulfillment = "Abholung" if order["fulfillment_type"] == "abholung" else "Lieferung"

    # ---- Styles ----
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
        leftMargin=1 * cm, rightMargin=1 * cm,
        topMargin=1 * cm, bottomMargin=1 * cm,
        title=f"Bestellung Nr. {order_id}",
    )

    # ---- Kopfzeile: links leer, Mitte Datum, rechts Uhrzeit + Art ----
    # Die äußeren Spalten sind gleich breit, damit das Datum wirklich mittig sitzt.
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

    # ---- Inhalt zusammenbauen ----
    story = [
        header,
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>{escape(order['customer_name'])}</b>", base),
    ]
    if order["delivery_address"]:
        story.append(Paragraph(escape(order["delivery_address"]), base))
    if order["customer_phone"]:
        story.append(Paragraph(escape(order["customer_phone"]), base))

    story.append(Paragraph("Bestellung", heading))
    for item in items:
        story.append(Paragraph(
            f"{item['quantity']} × {escape(item['product_name'])} "
            f"({escape(item['unit'])})",
            base,
        ))

    # NEU: Gesamtbetrag am Ende. escape() ist hier nicht nötig, weil euro()
    # nur Ziffern, Komma, Punkt und € liefert.
    if total_cents:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(f"<b>Gesamtbetrag: {euro(total_cents)}</b>", right))

    doc.build(story)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/pdf",
        download_name=f"Bestellung_{order_id}.pdf",
    )


# ===================================================================
# 11. Start
# ===================================================================
# Datenbank vorbereiten. Steht hier unten, damit alle Funktionen oben
# schon definiert sind.
init_db()

if __name__ == "__main__":
    # debug=True: automatischer Neustart bei Codeänderungen + Fehlerseite
    # im Browser. Für den echten Betrieb auf debug=False stellen.
    app.run(debug=True)