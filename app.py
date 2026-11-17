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
import re

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
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
        if "bundle_persons" not in spalten:
            db.execute(
                "ALTER TABLE products ADD COLUMN bundle_persons INTEGER")
    # order_items hat eigene Spalten, deshalb eine eigene Liste.
        positionsspalten = [zeile[1] for zeile in db.execute("PRAGMA table_info(order_items)")]
        if positionsspalten and "bundle_id" not in positionsspalten:
            db.execute("ALTER TABLE order_items ADD COLUMN bundle_id INTEGER")

    # 3c) schema.sql = Tabellenstruktur, produktliste.sql = Startinhalte.
    #     executescript führt mehrere SQL-Befehle hintereinander aus.
    #     Die Kundentabelle (Stammkunden) wird hier nur angelegt, nicht gefüllt.
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
        SELECT id, name, price_cents, unit, tax_rate, bundle_persons
        FROM products
        WHERE active = 1 AND name LIKE ?
        ORDER BY name
        """,
        (f"%{search_term}%",),
    ).fetchall()

    connection.close()
    return products

def search_customers(search_term):
    """
    Sucht Kunden, deren Name mit dem Suchbegriff BEGINNT oder bei denen
    ein Wort im Namen damit beginnt ("W" findet "Weber, Anna" und
    "Anna Weber").

    Verwendet in: customer_api()  ->  aufgerufen von order.js beim Tippen.

    LIKE 'W%'   = beginnt mit W
    LIKE '% W%' = ein späteres Wort beginnt mit W
    LIMIT 8 hält die Vorschlagsliste kurz.
    """
    connection = connect_db()

    customers = connection.execute(
        """
        SELECT id, name, address, phone
        FROM customers
        WHERE name LIKE ? OR name LIKE ?
        ORDER BY name
        LIMIT 8
        """,
        (f"{search_term}%", f"% {search_term}%"),
    ).fetchall()

    connection.close()
    return customers

def get_customers(search_term=""):
    """
    Liest alle Kunden, optional gefiltert.

    Verwendet in: kunden()

    Der Suchbegriff wird in Name, Telefon UND Adresse gesucht
    (LIKE '%begriff%' = enthält). Ohne Suchbegriff kommen alle Kunden.
    """
    connection = connect_db()

    if search_term:
        muster = f"%{search_term}%"
        customers = connection.execute(
            """
            SELECT id, name, phone, address
            FROM customers
            WHERE name LIKE ? OR phone LIKE ? OR address LIKE ?
            ORDER BY name
            """,
            (muster, muster, muster),
        ).fetchall()
    else:
        customers = connection.execute(
            "SELECT id, name, phone, address FROM customers ORDER BY name"
        ).fetchall()

    connection.close()
    return customers


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
               order_items.product_id, order_items.bundle_id,
               order_items.quantity, order_items.unit_price_cents
        FROM order_items
        JOIN products ON products.id = order_items.product_id
        WHERE order_items.order_id = ?
        ORDER BY order_items.id
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

def get_week_positions(start, ende):
    """
    Liefert jede einzelne Bestellposition des Zeitraums mit Kunde, Tag
    und Uhrzeit. Grundlage der Wochenansicht: pro Kategorie eine Tabelle.

    start/ende sind ISO-Text wie "2026-11-17" (BETWEEN auf Textvergleich).

    Sortierung: Kategorie, dann Produkt in der Reihenfolge der Preisliste
    (p.id), dann Tag und Uhrzeit. Dadurch stehen z. B. alle 10-kg-Spanferkel
    vor den 15-kg-Spanferkeln.

    Verwendet in: week_view()
    """
    connection = connect_db()
    rows = connection.execute(
        """
        SELECT p.id   AS product_id,
               p.name AS product_name,
               p.unit,
               COALESCE(c.name, 'Ohne Kategorie') AS category_name,
               COALESCE(c.sort_order, 9999)       AS category_sort,
               o.customer_name, o.order_date, o.order_time,
               oi.quantity, oi.bundle_id
        FROM order_items oi
        JOIN orders   o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE o.order_date BETWEEN ? AND ?
        ORDER BY COALESCE(c.sort_order, 9999), c.id, p.id,
                 o.order_date, o.order_time
        """,
        (start, ende),
    ).fetchall()
    connection.close()
    return rows

def resolve_week(datum_text):
    """
    Wandelt den date-Parameter der URL in die Woche um.

    Gibt (datum, montag, start, sonntag) zurück.
    start ist heute, wenn heute in dieser Woche liegt (vergangene Tage
    der laufenden Woche zählen nicht mehr), sonst der Montag.
    Bei ungültigem Datum wird heute genommen.

    Verwendet in: week_view(), week_pdf()
    """
    heute = date.today()

    try:
        datum = date.fromisoformat(datum_text)
    except ValueError:
        datum = heute

    montag, sonntag = week_range(datum)
    start = heute if montag <= heute <= sonntag else montag
    return datum, montag, start, sonntag


def get_week_categories(start, ende):
    """
    Gruppiert die Einzelpositionen des Zeitraums zu
    Kategorien -> Produkte -> Positionen.

    start/ende sind ISO-Text wie "2026-11-17".
    Die Sortierung kommt schon aus dem SQL, deshalb reicht der Vergleich
    mit dem zuletzt angelegten Eintrag.

    Verwendet in: week_view(), week_pdf()
    """
    kategorien = []
    for row in get_week_positions(start, ende):
        if not kategorien or kategorien[-1]["name"] != row["category_name"]:
            kategorien.append({
                "name": row["category_name"],
                # Nur beim Spanferkel gibt es die zusätzliche kg-Spalte.
                "mit_kg": row["category_name"] == "Spanferkel",
                "produkte": [],
            })
        kategorie = kategorien[-1]

        if not kategorie["produkte"] \
                or kategorie["produkte"][-1]["id"] != row["product_id"]:
            # "Spanferkel 10 kg (ca. 10–12 Personen)" -> "10 kg"
            treffer = re.search(r"(\d+(?:,\d+)?)\s*kg", row["product_name"])
            kategorie["produkte"].append({
                "id": row["product_id"],
                "name": row["product_name"],
                "unit": row["unit"],
                "kg": f"{treffer.group(1)} kg" if treffer else "–",
                "total": 0,
                "positionen": [],
            })
        produkt = kategorie["produkte"][-1]

        tag = date.fromisoformat(row["order_date"])
        produkt["total"] += row["quantity"]
        produkt["positionen"].append({
            "kunde": row["customer_name"],
            "tag": f"{WEEKDAYS[tag.weekday()][:2]}, {tag.strftime('%d.%m.')}",
            "uhrzeit": row["order_time"],
            "anzahl": row["quantity"],
            "im_buefett": row["bundle_id"] is not None,
        })

    return kategorien

def get_bundle_components(bundle_id, persons):
    """
    Liefert die Bestandteile eines Sammelprodukts mit fertig
    berechneter Menge (Stück pro Person × Personenzahl).
    Verwendet in: product_api()
    """
    connection = connect_db()
    rows = connection.execute(
        """
        SELECT p.id, p.name, p.unit, bi.quantity_per_person
        FROM bundle_items bi
        JOIN products p ON p.id = bi.component_id
        WHERE bi.bundle_id = ? AND p.active = 1
        ORDER BY p.name
        """,
        (bundle_id,),
    ).fetchall()
    connection.close()
    return [
        {"id": r["id"], "name": r["name"], "unit": r["unit"],
         "per_person": r["quantity_per_person"],
         "quantity": r["quantity_per_person"] * persons}
        for r in rows
    ]

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
# 7b. Routen: Kunden
# ===================================================================
@app.route("/kunden")
def kunden():
    """
    Kundenliste mit Formular zum Anlegen. Datei: kunden.html
    Optionale Suche über die URL:  /kunden?q=weber
    """
    search_term = request.args.get("q", "").strip()

    return render_template(
        "kunden.html",
        customers=get_customers(search_term),
        search_term=search_term,
        hinweis=request.args.get("hinweis"),
        fehler=request.args.get("fehler"),
    )


@app.route("/kunden/hinzufuegen", methods=["POST"])
def kunde_hinzufuegen():
    """
    Legt einen neuen Kunden an.
    Abgeschickt von: dem Formular in kunden.html.
    """
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    def zurueck_url(**kwargs):
        return redirect(url_for("kunden", **kwargs))

    if not name:
        return zurueck_url(fehler="Bitte einen Namen eingeben.")

    if not phone:
        return zurueck_url(fehler="Bitte eine Telefonnummer eingeben.")

    connection = connect_db()
    try:
        connection.execute(
            "INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)",
            (name, phone, address),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        # UNIQUE (name, phone) in schema.sql hat zugeschlagen.
        connection.close()
        return zurueck_url(
            fehler=f"„{name}“ mit dieser Telefonnummer gibt es schon."
        )

    connection.close()
    return zurueck_url(hinweis=f"„{name}“ wurde hinzugefügt.")


@app.route("/kunden/<int:customer_id>/bearbeiten", methods=["GET", "POST"])
def kunde_bearbeiten(customer_id):
    """
    Zeigt ein vorausgefülltes Formular und speichert die Änderungen.
    Datei: kunde_edit.html
    Aufgerufen von: dem ✏️-Knopf in kunden.html.

    GET  = Formular anzeigen (Werte aus der Datenbank)
    POST = Änderungen speichern (Werte aus dem Formular)

    Alte Bestellungen bleiben unverändert: sie haben ihre eigene Kopie
    von Name, Adresse und Telefon.
    """
    connection = connect_db()

    customer = connection.execute(
        "SELECT id, name, phone, address FROM customers WHERE id = ?",
        (customer_id,),
    ).fetchone()

    if customer is None:
        connection.close()
        return redirect(url_for("kunden", fehler="Kunde nicht gefunden."))

    def zeige_formular(werte, fehler_text=None):
        """
        Rendert kunde_edit.html. 'werte' enthält die anzuzeigenden
        Feldinhalte – beim GET die gespeicherten, beim POST die gerade
        eingegebenen (damit bei einem Fehler nichts verloren geht).
        """
        connection.close()
        return render_template(
            "kunde_edit.html",
            customer=werte,
            fehler=fehler_text,
        )

    # ---------- GET: nur anzeigen ----------
    if request.method == "GET":
        return zeige_formular(dict(customer))

    # ---------- POST: speichern ----------
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    werte = {"id": customer_id, "name": name, "phone": phone, "address": address}

    if not name:
        return zeige_formular(werte, "Bitte einen Namen eingeben.")

    if not phone:
        return zeige_formular(werte, "Bitte eine Telefonnummer eingeben.")

    try:
        connection.execute(
            "UPDATE customers SET name = ?, phone = ?, address = ? WHERE id = ?",
            (name, phone, address, customer_id),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        # Ein ANDERER Kunde hat schon genau diesen Namen + diese Nummer.
        return zeige_formular(
            werte, f"„{name}“ mit dieser Telefonnummer gibt es schon."
        )

    connection.close()
    return redirect(url_for("kunden", hinweis=f"„{name}“ wurde gespeichert."))


@app.route("/kunden/<int:customer_id>/loeschen", methods=["POST"])
def kunde_loeschen(customer_id):
    """
    Löscht einen Kunden aus dem Kundenstamm.
    Abgeschickt von: dem 🗑️-Knopf in kunden.html.

    Hier ist ein echtes DELETE richtig: Bestellungen verweisen nicht auf
    die customers-Tabelle, sondern tragen ihre Kundendaten selbst.
    Alte Aufträge und PDFs bleiben also vollständig.
    """
    connection = connect_db()

    row = connection.execute(
        "SELECT name FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()

    if row is None:
        connection.close()
        return redirect(url_for("kunden", fehler="Kunde nicht gefunden."))

    connection.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    connection.commit()
    connection.close()

    return redirect(url_for("kunden", hinweis=f"„{row['name']}“ wurde gelöscht."))


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
    result = []
    for product in products:
        eintrag = {
            "id": product["id"],
            "name": product["name"],
            "price_cents": product["price_cents"],
            "unit": product["unit"],
            "tax_rate": product["tax_rate"],
            "bundle_persons": product["bundle_persons"],
        }
        if product["bundle_persons"]:
            eintrag["components"] = get_bundle_components(
                product["id"], product["bundle_persons"]
            )
        result.append(eintrag)
    return jsonify(result)

@app.route("/api/customers")
def customer_api():
    """
    Liefert Kundenvorschläge als JSON an order.js.
    Aufgerufen von: order.js beim Tippen ins Feld "Kundenname" (fetch).
    Antwort z. B.: [{"id": 3, "name": "Anna Weber", "address": "...", "phone": "..."}]
    """
    search_term = request.args.get("query", "").strip()
    if not search_term:
        return jsonify([])

    return jsonify([
        {
            "id": kunde["id"],
            "name": kunde["name"],
            "address": kunde["address"],
            "phone": kunde["phone"],
        }
        for kunde in search_customers(search_term)
    ])


@app.route("/api/orders", methods=["POST"])
def order_api():
    """
    Speichert eine Bestellung samt Positionen.
    Aufgerufen von: order.js beim Absenden des Formulars (fetch, JSON body).

    Alles passiert in EINER Verbindung. Entweder wird der Auftrag mit allen
    Positionen gespeichert – oder bei einem Fehler gar nichts. Man nennt das
    eine Transaktion: kein halb gespeicherter Auftrag ohne Positionen.

    Der Kundenstamm (customers) wird hier bewusst NICHT verändert. Stammkunden
    werden nur auf der Seite /kunden gepflegt.
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

        # Welche Produkte wurden "normal" bestellt? Nur deren Bestandteile
        # dürfen später mit Preis 0 gespeichert werden.
        normal_ids = {int(i["product_id"]) for i in items if not i.get("bundle_id")}

        # 2) Die Positionen speichern.
        for item in items:
            product_id = int(item["product_id"])
            quantity = int(item["quantity"])
            if quantity < 1:
                raise ValueError("Die Menge muss mindestens 1 sein.")

            # Gehört die Position zu einem Büfett? None = normale Position.
            bundle_id = item.get("bundle_id")
            bundle_id = int(bundle_id) if bundle_id else None

            if bundle_id:
                # Bestandteil eines Büfetts: Preis 0, aber nur, wenn er
                # wirklich zu einem mitbestellten Büfett gehört.
                gehoert_dazu = connection.execute(
                    "SELECT 1 FROM bundle_items "
                    "WHERE bundle_id = ? AND component_id = ?",
                    (bundle_id, product_id),
                ).fetchone()
                if bundle_id not in normal_ids or gehoert_dazu is None:
                    raise ValueError("Ungültiger Büfett-Bestandteil.")
                price_cents = 0
            else:
                # Preis aus der DATENBANK lesen, nicht aus dem Browser.
                product = connection.execute(
                    "SELECT price_cents FROM products WHERE id = ?", (product_id,)
                ).fetchone()
                if product is None:
                    raise ValueError("Ein ausgewähltes Produkt existiert nicht mehr.")
                price_cents = product["price_cents"]

            connection.execute(
                """
                INSERT INTO order_items
                    (order_id, product_id, quantity, unit_price_cents, bundle_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, product_id, quantity, price_cents, bundle_id),
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
    Wochenansicht: pro Kategorie eine Tabelle mit allen Einzelbestellungen.
    Datei: wochenansicht.html

    Datum aus der URL:  /wochenansicht?date=2026-11-12
    Daraus wird die Woche ermittelt (Montag..Sonntag), in der es liegt.
    Ohne Datum: aktuelle Woche.

    Liegt heute in dieser Woche, beginnt die Auswertung erst bei heute
    (siehe resolve_week).
    """
    datum, montag, start, sonntag = resolve_week(
        request.args.get("date", date.today().isoformat())
    )

    # Kennzahlen (Anzahl Bestellungen, Umsatz) wie bisher.
    rows, bestellungen, kunden = get_week_summary(
        start.isoformat(), sonntag.isoformat()
    )
    gesamt_cents = sum(row["total_cents"] for row in rows)

    kategorien = get_week_categories(start.isoformat(), sonntag.isoformat())

    # Vor/Zurück-Links im Template brauchen fertige URLs.
    vorherige = (montag - timedelta(days=7)).isoformat()
    naechste = (montag + timedelta(days=7)).isoformat()

    return render_template(
        "wochenansicht.html",
        selected_date=datum.isoformat(),
        montag=montag,
        start=start,
        sonntag=sonntag,
        kalenderwoche=montag.isocalendar()[1],
        kategorien=kategorien,
        bestellungen=bestellungen,
        kunden=kunden,
        gesamt_cents=gesamt_cents,
        vorherige=vorherige,
        naechste=naechste,
    )

@app.route("/wochenansicht/pdf")
def week_pdf():
    """
    Erzeugt ein A4-PDF der Wochenansicht: pro Kategorie eine eigene Seite.
    Aufgerufen von: dem PDF-Knopf in wochenansicht.html (neuer Tab).

    Der Zeitraum kommt aus denselben Funktionen wie in der Ansicht,
    das PDF zeigt also genau das, was auf dem Bildschirm steht.
    """
    datum, montag, start, sonntag = resolve_week(
        request.args.get("date", date.today().isoformat())
    )
    kategorien = get_week_categories(start.isoformat(), sonntag.isoformat())

    kalenderwoche = montag.isocalendar()[1]
    zeitraum = (f"KW {kalenderwoche} · "
                f"{start.strftime('%d.%m.%Y')} – {sonntag.strftime('%d.%m.%Y')}")

    # ---- Styles ----
    base = ParagraphStyle("wbase", fontName="ComicSans", fontSize=10, leading=13)
    bold = ParagraphStyle("wbold", parent=base, fontName="ComicSans-Bold")
    titel = ParagraphStyle("wtitel", parent=base, fontName="ComicSans-Bold",
                           fontSize=20, leading=24)
    klein = ParagraphStyle("wklein", parent=base, textColor=colors.grey)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"Wochenansicht KW {kalenderwoche}",
    )

    story = []

    if not kategorien:
        story.append(Paragraph("Wochenansicht", titel))
        story.append(Paragraph(escape(zeitraum), klein))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("In diesem Zeitraum gibt es keine Bestellungen.", base))

    for index, kategorie in enumerate(kategorien):
        # Jede Kategorie beginnt auf einer neuen Seite.
        if index > 0:
            story.append(PageBreak())

        story.append(Paragraph(escape(kategorie["name"]), titel))
        story.append(Paragraph(escape(zeitraum), klein))
        story.append(Spacer(1, 0.5 * cm))

        mit_kg = kategorie["mit_kg"]
        spalten = 5 if mit_kg else 4

        # Gesamtbreite 18 cm (A4 minus Ränder).
        if mit_kg:
            breiten = [6.5 * cm, 3.5 * cm, 3 * cm, 2.5 * cm, 2.5 * cm]
        else:
            breiten = [8 * cm, 3.5 * cm, 3 * cm, 3.5 * cm]

        kopf = ["Kundenname", "Tag", "Uhrzeit"]
        if mit_kg:
            kopf.append("kg")
        kopf.append("Anzahl")

        daten = [[Paragraph(text, bold) for text in kopf]]
        stil = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ]

        for produkt in kategorie["produkte"]:
            # Zwischenüberschrift: Produktname über alle Spalten.
            zeile = len(daten)
            daten.append([Paragraph(escape(produkt["name"]), bold)]
                         + [""] * (spalten - 1))
            stil.append(("SPAN", (0, zeile), (-1, zeile)))
            stil.append(("BACKGROUND", (0, zeile), (-1, zeile),
                         colors.HexColor("#e8e8e0")))

            for pos in produkt["positionen"]:
                anzahl = str(pos["anzahl"])
                if pos["im_buefett"]:
                    anzahl += " (im Büfett)"

                zellen = [
                    Paragraph(escape(pos["kunde"]), base),
                    Paragraph(escape(pos["tag"]), base),
                    Paragraph(f"{escape(pos['uhrzeit'])} Uhr", base),
                ]
                if mit_kg:
                    zellen.append(Paragraph(escape(produkt["kg"]), base))
                zellen.append(Paragraph(escape(anzahl), base))
                daten.append(zellen)

            # Summenzeile: "Gesamt" links, Summe unter "Anzahl".
            zeile = len(daten)
            daten.append([Paragraph("Gesamt", bold)]
                         + [""] * (spalten - 2)
                         + [Paragraph(str(produkt["total"]), bold)])
            stil.append(("SPAN", (0, zeile), (spalten - 2, zeile)))
            stil.append(("LINEBELOW", (0, zeile), (-1, zeile), 0.5, colors.grey))

        tabelle = Table(daten, colWidths=breiten, repeatRows=1)
        tabelle.setStyle(TableStyle(stil))
        story.append(tabelle)

    doc.build(story)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/pdf",
        download_name=f"Wochenansicht_KW{kalenderwoche}.pdf",
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

    # Bestehende Positionen mit Produktnamen und Büfett-Zuordnung.
    items = lade_positionen(connection, order_id)

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

            # Ist das Produkt schon als NORMALE Position in dieser Bestellung?
            # (bundle_id IS NULL: Büfett-Bestandteile zählen hier nicht.)
            # Dann nur die Menge erhöhen und den DAMALIGEN Preis stehen lassen.
            vorhanden = connection.execute(
                "SELECT id FROM order_items "
                "WHERE order_id = ? AND product_id = ? AND bundle_id IS NULL",
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

        # ---- Bestandteile neu hinzugefügter Büfetts ----
        # order_edit.js nennt diese Felder neu_teil_<büfett-id>_<produkt-id>.
        # Läuft NACH den normalen Positionen, damit das Büfett schon existiert.
        for feldname, wert in list(request.form.items()):
            if not feldname.startswith("neu_teil_"):
                continue

            # Aus "neu_teil_5_12" Büfett 5 und Produkt 12 herausschneiden.
            try:
                _, _, buffet_text, produkt_text = feldname.split("_")
                buffet_id = int(buffet_text)
                produkt_id = int(produkt_text)
                menge = int(wert)
            except ValueError:
                continue

            if menge < 1:
                continue

            # Preis 0 nur, wenn das Produkt wirklich zu diesem Büfett gehört
            # UND das Büfett in dieser Bestellung vorkommt.
            gehoert_dazu = connection.execute(
                "SELECT 1 FROM bundle_items WHERE bundle_id = ? AND component_id = ?",
                (buffet_id, produkt_id),
            ).fetchone()
            buffet_da = connection.execute(
                "SELECT 1 FROM order_items "
                "WHERE order_id = ? AND product_id = ? AND bundle_id IS NULL",
                (order_id, buffet_id),
            ).fetchone()
            if gehoert_dazu is None or buffet_da is None:
                continue

            vorhanden = connection.execute(
                "SELECT id FROM order_items "
                "WHERE order_id = ? AND product_id = ? AND bundle_id = ?",
                (order_id, produkt_id, buffet_id),
            ).fetchone()

            if vorhanden:
                connection.execute(
                    "UPDATE order_items SET quantity = quantity + ? WHERE id = ?",
                    (menge, vorhanden["id"]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, quantity, unit_price_cents, bundle_id)
                    VALUES (?, ?, ?, 0, ?)
                    """,
                    (order_id, produkt_id, menge, buffet_id),
                )

        # Büfett auf Menge 0 gesetzt (gelöscht)? Dann dürfen seine
        # Bestandteile nicht als Waisen in der Bestellung bleiben.
        connection.execute(
            """
            DELETE FROM order_items
            WHERE order_id = ? AND bundle_id IS NOT NULL
              AND bundle_id NOT IN (
                  SELECT product_id FROM order_items
                  WHERE order_id = ? AND bundle_id IS NULL
              )
            """,
            (order_id, order_id),
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
        items = lade_positionen(connection, order_id)

        return zeige_formular(neue_werte, [dict(i) for i in items], str(fehler))

    connection.close()

    # Zur Tagesansicht des (evtl. geänderten) Datums springen.
    return redirect(url_for(
        "day_view",
        date=order_date,
        hinweis=f"Bestellung Nr. {order_id} wurde gespeichert.",
    ))

def lade_positionen(connection, order_id):
    """
    Positionen einer Bestellung inkl. Büfett-Zuordnung.
    per_person = Stück pro Person, nur bei Büfett-Bestandteilen gefüllt.
    Verwendet in: order_bearbeiten()
    """
    return connection.execute(
        """
        SELECT order_items.id, order_items.product_id, order_items.bundle_id,
               order_items.quantity, order_items.unit_price_cents,
               products.name, products.unit,
               bi.quantity_per_person AS per_person
        FROM order_items
        JOIN products ON products.id = order_items.product_id
        LEFT JOIN bundle_items bi
               ON bi.bundle_id = order_items.bundle_id
              AND bi.component_id = order_items.product_id
        WHERE order_items.order_id = ?
        ORDER BY order_items.id
        """,
        (order_id,),
    ).fetchall()

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
    
    bundle_style = ParagraphStyle("bundle", parent=base, fontName="ComicSans-Bold",
                                alignment=TA_RIGHT, spaceBefore=6)

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
    bundle_ids = {item["bundle_id"] for item in items if item["bundle_id"]}

    def position_text(item):
        return (f"{item['quantity']} × {escape(item['product_name'])} "
                f"({escape(item['unit'])})")

    for item in items:
        if item["bundle_id"]:
            continue    # Bestandteile werden unter ihrem Büfett ausgegeben

        if item["product_id"] in bundle_ids:
            # "Fingerfood Büfett ab 10 Personen" -> "Fingerfood Büfett"
            basis = re.sub(r"\s+ab\s+\d+\s+Personen?$", "", item["product_name"])
            wort = "Person" if item["quantity"] == 1 else "Personen"
            story.append(Paragraph(
                f"{escape(basis)} für {item['quantity']} {wort}", bundle_style
            ))
            for teil in items:
                if teil["bundle_id"] == item["product_id"]:
                    story.append(Paragraph(position_text(teil), base))
        else:
            story.append(Paragraph(position_text(item), base))

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