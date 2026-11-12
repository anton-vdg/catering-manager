// =====================================================================
// order.js – Logik der Bestellseite (home.html)
//
// Diese Datei wird von der Route order_script() in app.py ausgeliefert
// und in home.html eingebunden:  <script src="/order.js"></script>
//
// Aufgaben:
//   1. Produktsuche -> fragt /api/products
//   2. Auswahl merken -> Map im Browser, nichts wird gespeichert
//   3. Mengen und Summen berechnen (brutto, MwSt. herausgerechnet)
//   4. Absenden -> POST an /api/orders, dann erst wird gespeichert
// =====================================================================


// ---------------------------------------------------------------------
// 1. HTML-Elemente einmal suchen und merken
// ---------------------------------------------------------------------
// querySelector("#id") sucht das Element mit id="id".
// Einmal suchen reicht – danach ist es in der Variablen gespeichert.
const orderForm = document.querySelector("#order-form");
const searchInput = document.querySelector("#produktsuche");
const searchResults = document.querySelector("#suchergebnisse");
const orderItems = document.querySelector("#bestellpositionen");
const totalElement = document.querySelector("#gesamtbetrag");
const taxElement = document.querySelector("#mwst-betrag");
const saveHint = document.querySelector("#speicherhinweis");


// ---------------------------------------------------------------------
// 2. Zustand: welche Produkte sind ausgewählt?
// ---------------------------------------------------------------------
// Map = Schlüssel-Wert-Speicher. Schlüssel ist die Produkt-ID,
// Wert ist das Produktobjekt plus der aktuellen Menge.
// Beispiel: 5 -> { id: 5, name: "Ente", price_cents: 4000, quantity: 2 }
//
// Wichtig: Das lebt nur im Browser. Erst beim Absenden wird gespeichert.
const selectedProducts = new Map();


// ---------------------------------------------------------------------
// 3. Kleine Hilfsfunktionen
// ---------------------------------------------------------------------

function formatCents(cents) {
  // 4000 -> "40,00"
  // toFixed(2) macht zwei Nachkommastellen, replace tauscht Punkt gegen Komma.
  return (cents / 100).toFixed(2).replace(".", ",");
}

function parseQuantity(raw) {
  // Liest den Inhalt eines Eingabefelds als ganze Zahl.
  // Leer, Text oder negativ -> 0. Wird gebraucht, damit beim Tippen
  // keine Fehler entstehen, wenn das Feld kurz leer ist.
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) {
    return 0;
  }
  return Math.floor(n);
}

function calculateTax(product) {
  // MwSt. aus einem BRUTTO-Preis herausrechnen.
  // Formel: Steuer = brutto × satz / (100 + satz)
  //
  // Beispiel: 100,00 € brutto bei 19 %
  //   10000 × 19 / 119 = 1596 Cent = 15,96 € Steuer
  //
  // product.tax_rate kommt aus /api/products. Fehlt das Feld,
  // ergibt die Rechnung NaN – deshalb liefert die API es immer mit.
  const gross = product.price_cents * product.quantity;
  return Math.round((gross * product.tax_rate) / (100 + product.tax_rate));
}

function updateSummary() {
  // Aktualisiert NUR Gesamtbetrag und MwSt.
  //
  // Bewusst wird hier NICHT showOrderItems() aufgerufen: das würde die
  // ganze Liste neu bauen, das Eingabefeld ersetzen und den Cursor
  // verlieren. Deshalb berechnet diese Funktion nur die Zahlen.
  let totalCents = 0;
  let totalTaxCents = 0;

  for (const product of selectedProducts.values()) {
    // quantity kann während des Tippens kurz 0 sein – dann zählt
    // die Position in diesem Moment nichts.
    totalCents += product.price_cents * product.quantity;
    totalTaxCents += calculateTax(product);
  }

  // totalCents ist bereits brutto – die Steuer wird nur angezeigt,
  // nicht noch einmal addiert.
  totalElement.textContent = `Gesamtbetrag: ${formatCents(totalCents)} €`;
  taxElement.textContent = `MwSt.: ${formatCents(totalTaxCents)} €`;
}


// ---------------------------------------------------------------------
// 4. Produktsuche
// ---------------------------------------------------------------------

// "input" feuert bei jedem Tastendruck im Suchfeld.
searchInput.addEventListener("input", async () => {
  const searchTerm = searchInput.value.trim();

  // Leeres Feld: alte Treffer löschen und fertig.
  if (!searchTerm) {
    searchResults.replaceChildren();
    return;
  }

  // encodeURIComponent macht Sonderzeichen URL-sicher (z. B. "&" oder "ü").
  // await wartet, bis Python geantwortet hat. Deshalb ist die Funktion async.
  const response = await fetch(
    `/api/products?query=${encodeURIComponent(searchTerm)}`
  );

  if (!response.ok) {
    searchResults.textContent = "Suche fehlgeschlagen.";
    return;
  }

  // .json() verwandelt die Antwort in eine JavaScript-Liste.
  const products = await response.json();
  showSearchResults(products);
});

function showSearchResults(products) {
  // Baut die Trefferliste mit je einer Checkbox pro Produkt.
  // Wird von der Suche oben aufgerufen.
  searchResults.replaceChildren();

  if (products.length === 0) {
    searchResults.textContent = "Keine passenden Produkte gefunden.";
    return;
  }

  for (const product of products) {
    const label = document.createElement("label");
    label.className = "produkt-treffer";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.productId = product.id;

    // War das Produkt schon ausgewählt (z. B. nach erneuter Suche)?
    // Dann Häkchen wieder setzen.
    checkbox.checked = selectedProducts.has(product.id);

    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        // Neu ausgewählt: mit Startmenge 1 übernehmen.
        // ...product kopiert alle Felder (id, name, price_cents, ...).
        selectedProducts.set(product.id, { ...product, quantity: 1 });
      } else {
        // Abgewählt: aus der Map entfernen.
        selectedProducts.delete(product.id);
      }
      showOrderItems();
    });

    label.append(
      checkbox,
      ` ${product.name} – ${formatCents(product.price_cents)} € pro ${product.unit}`
    );
    searchResults.append(label);
  }
}


// ---------------------------------------------------------------------
// 5. Bestellliste aufbauen
// ---------------------------------------------------------------------

function showOrderItems() {
  // Baut die Liste "Bestellte Produkte" komplett neu aus selectedProducts.
  // Wird aufgerufen bei: Auswahl ändern, Menge verlassen, Entfernen,
  //                      nach dem Speichern.
  //
  // WICHTIG: Beim Tippen in ein Mengenfeld darf diese Funktion NICHT
  // laufen – sonst wird das Feld ersetzt und der Cursor springt raus.
  // Dafür gibt es updateSummary().
  orderItems.replaceChildren();

  // Nach einer neuen Suche sind die Checkboxen neu – Häkchen nachziehen.
  document.querySelectorAll("[data-product-id]").forEach((checkbox) => {
    checkbox.checked = selectedProducts.has(Number(checkbox.dataset.productId));
  });

  if (selectedProducts.size === 0) {
    orderItems.textContent = "Noch kein Produkt ausgewählt.";
    updateSummary();
    return;
  }

  for (const product of selectedProducts.values()) {
    const row = document.createElement("div");
    row.className = "bestellposition";

    // Name und Einzelpreis.
    const name = document.createElement("span");
    name.textContent = `${product.name} (${formatCents(product.price_cents)} €)`;

    // Mengenfeld.
    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.value = product.quantity;

    // Beim Klick ins Feld wird der Inhalt markiert.
    // Dann ersetzt "20" tippen die 1 direkt, statt "120" zu ergeben.
    quantity.addEventListener("focus", () => {
      // setTimeout(..., 0): der Klick ist dann vorbei. Ohne das
      // hebt der Browser die Markierung sofort wieder auf.
      setTimeout(() => quantity.select(), 0);
    });

    // Während des Tippens: nur rechnen, Feld nicht anfassen.
    quantity.addEventListener("input", () => {
      product.quantity = parseQuantity(quantity.value);
      updateSummary();
    });

    // Feld verlassen oder Enter: jetzt auf gültig ≥ 1 bringen.
    quantity.addEventListener("change", () => {
      product.quantity = Math.max(1, parseQuantity(quantity.value));
      quantity.value = product.quantity;
      updateSummary();
    });

    // Entfernen-Knopf.
    const removeButton = document.createElement("button");
    removeButton.type = "button";  // "button" = löst kein Formular-Absenden aus
    removeButton.textContent = "Entfernen";
    removeButton.addEventListener("click", () => {
      selectedProducts.delete(product.id);
      showOrderItems();
    });

    row.append(name, quantity, removeButton);
    orderItems.append(row);
  }

  updateSummary();
}


// ---------------------------------------------------------------------
// 6. Absenden
// ---------------------------------------------------------------------

orderForm.addEventListener("submit", async (event) => {
  // Verhindert das normale Absenden (Seite neu laden).
  event.preventDefault();

  saveHint.textContent = "";

  const selectedFulfillment = document.querySelector('input[name="art"]:checked');

  const orderData = {
    customer_name: document.querySelector("#kundenname").value.trim(),
    delivery_address: document.querySelector("#adresse").value.trim(),
    customer_phone: document.querySelector("#telefon").value.trim(),
    order_date: document.querySelector("#datum").value,
    order_time: document.querySelector("#uhrzeit").value,
    fulfillment_type: selectedFulfillment ? selectedFulfillment.value : "",

    // Nur ID und Menge senden. Den Preis liest Python selbst aus der
    // Datenbank – so kann niemand über die Browser-Konsole Preise ändern.
    //
    // Math.max(1, ...) ist wichtig: hat jemand "0" getippt und direkt
    // auf Speichern geklickt, ohne das Feld zu verlassen, steht in
    // product.quantity noch 0. Python würde das ablehnen.
    items: [...selectedProducts.values()].map((product) => ({
      product_id: product.id,
      quantity: Math.max(1, product.quantity),
    })),
  };

  const response = await fetch("/api/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },  // "Ich schicke JSON"
    body: JSON.stringify(orderData),                  // JS-Objekt -> JSON-Text
  });

  const result = await response.json();

  // Alles außerhalb 200–299 ist ein Fehler.
  if (!response.ok) {
    saveHint.textContent = result.error || "Speichern fehlgeschlagen.";
    return;
  }

  // Erfolg: Formular leeren und Auswahl zurücksetzen.
  saveHint.textContent = `Bestellung Nr. ${result.order_id} wurde gespeichert.`;
  orderForm.reset();
  selectedProducts.clear();
  searchResults.replaceChildren();
  showOrderItems();   // setzt die Summen wieder auf 0,00 €
});