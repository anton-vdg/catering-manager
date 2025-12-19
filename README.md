# Partyservice Manager

Eine einfache, lokale Bestell- und Rechnungsverwaltung für einen Partyservice / Catering-Betrieb.  
Bestellungen werden digital erfasst, gespeichert und können als PDF-Rechnung ausgegeben werden.

Die Anwendung läuft **lokal** (keine Cloud, kein Internet nötig) auf Basis von **Python, Streamlit und SQLite**.

---

## Funktionen

- Neue Bestellungen anlegen (Datum, Uhrzeit, Abholung/Lieferung)
- Kundenverwaltung (Name, Telefon, Adresse)
- Produkt- / Artikelstamm mit Standardpreis, MwSt und Einheit
- Bestellpositionen mit Menge, Preis und MwSt
- Tagesliste aller Bestellungen
- Auftragsstatus (`open`, `paid`)
- Zahlungsart (Bar, Karte, Überweisung, …)
- Rechnungsnummern automatisch vergeben
- Rechnung als **PDF** erzeugen
- Bestellungen löschen (inkl. Positionen)
- Alle Daten lokal in einer SQLite-Datei gespeichert

---

## Projektstruktur

partyservice-manager/
├─ app.py 
├─ db.py 
├─ invoice_pdf.py 
├─ schema.sql 
├─ requirements.txt
├─ partyservice.db (wird automatisch erzeugt, wenn nicht vorhanden)
├─ README.md

---

## Voraussetzungen

- Python **3.10 oder höher**
- Keine externe Datenbank notwendig (SQLite wird lokal verwendet)

---

## Installation

### 1) Repository klonen oder Projektordner kopieren
```bash
git clone [<repo-url>](https://github.com/anton-vdg/catering-orders.git)
cd catering-orders

### 2) Virtuelle Umgebung anlegen
```
python -m venv partyenv
```
### 3) Abhängigkeiten installieren
```
partyenv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Datenhaltung

- Alle Daten liegen in der Datei `partyservice.db`.

---

## Rechnungen

- Rechnungsnummern werden automatisch fortlaufend vergeben
- Rechnungen werden als PDF erzeugt
- Die PDF enthält:
  - Firmendaten (in `invoice_pdf.py` anpassbar)
  - Kundendaten
  - Bestellung
  - MwSt-Aufschlüsselung
  - Gesamtbetrag

---

## Statuslogik
- **Auftragsstatus:** `open` -> `paid`
- **Zahlungsart:** Bar/Karte/Überweisung

---

## Produktliste
- Produkte dienen als Vorlage
- Preis, MwSt und Einheit werden beim Anlegen einer Position kopiert
- Änderungen am Produkt wirken nicht rückwirkend auf bestehende Rechnungen

---

## Lizenz / Nutzung
- Für private oder interne geschäftliche Nutzung
