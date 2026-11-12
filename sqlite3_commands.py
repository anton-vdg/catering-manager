import sqlite3

# Verbindung zur Datenbank herstellen
connection = sqlite3.connect("products.db")
cursor = connection.cursor()

# ALTER TABLE ausführen
cursor.execute("""
ALTER TABLE products ADD COLUMN tax_rate INTEGER NOT NULL CHECK (tax_rate IN (7, 19)) DEFAULT 19;
""")

# Änderungen speichern und Verbindung schließen
connection.commit()
connection.close()

print("Spalte 'tax_rate' erfolgreich hinzugefügt.")