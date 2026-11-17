import sqlite3

# Verbindung zur Datenbank herstellen
connection = sqlite3.connect("products.db")

# Nur der Kundenstamm wird geleert. Bestellungen bleiben unberührt,
# weil sie ihre Kundendaten selbst tragen.
connection.execute("DELETE FROM customers")
connection.commit()
connection.close()

print("Kundenstamm geleert.")