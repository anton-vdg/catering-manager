// Die benötigten HTML-Elemente einmal über ihre IDs finden.
const orderForm = document.querySelector("#order-form");
const searchInput = document.querySelector("#produktsuche");
const searchResults = document.querySelector("#suchergebnisse");
const orderItems = document.querySelector("#bestellpositionen");
const totalElement = document.querySelector("#gesamtbetrag");
const saveHint = document.querySelector("#speicherhinweis");

// Die Map speichert die im Browser ausgewählten Produkte: ID -> Produktdaten.
const selectedProducts = new Map();

searchInput.addEventListener("input", async () => {
  // Den Suchtext lesen und Leerzeichen entfernen.
  const searchTerm = searchInput.value.trim();

  if (!searchTerm) {
    searchResults.replaceChildren();
    return;
  }

  // Python per URL aufrufen; encodeURIComponent macht Sonderzeichen URL-sicher.
  const response = await fetch(`/api/products?query=${encodeURIComponent(searchTerm)}`);
  // Die JSON-Antwort von Python in eine JavaScript-Liste verwandeln.
  const products = await response.json();
  showSearchResults(products);
});

function showSearchResults(products) {
  // Alte Treffer entfernen, bevor neue angezeigt werden.
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
    checkbox.checked = selectedProducts.has(product.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        // Produkt mit Startmenge 1 zur Bestellung hinzufügen.
        selectedProducts.set(product.id, { ...product, quantity: 1 });
      } else {
        // Abgewähltes Produkt aus der Bestellung entfernen.
        selectedProducts.delete(product.id);
      }
      showOrderItems();
    });

    const price = formatCents(product.price_cents);
    label.append(checkbox, ` ${product.name} – ${price} € pro ${product.unit}`);
    searchResults.append(label);
  }
}

const taxElement = document.querySelector("#mwst-betrag");

function calculateTax(product) {
  // MwSt. steckt im Bruttopreis: Steuer = brutto * satz / (100 + satz)
  const gross = product.price_cents * product.quantity;
  return Math.round((gross * product.tax_rate) / (100 + product.tax_rate));
}

function showOrderItems() {
  // Bestellliste aus dem aktuellen Zustand neu aufbauen.
  orderItems.replaceChildren();

  document.querySelectorAll("[data-product-id]").forEach((checkbox) => {
    checkbox.checked = selectedProducts.has(Number(checkbox.dataset.productId));
  });

  if (selectedProducts.size === 0) {
    orderItems.textContent = "Noch kein Produkt ausgewählt.";
    updateSummary();
    return;
  }

  let totalCents = 0;
  let totalTaxCents = 0;

  for (const product of selectedProducts.values()) {
    const row = document.createElement("div");
    row.className = "bestellposition";

    const name = document.createElement("span");
    name.textContent = `${product.name} (${formatCents(product.price_cents)} €)`;

    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.value = product.quantity;

    // Klick ins Feld markiert den Inhalt, damit man ihn direkt überschreiben
    // kann – statt erst "120" zu tippen und die führende 1 zu löschen.
    quantity.addEventListener("focus", () => {
      // setTimeout: der Klick, der den Fokus gesetzt hat, ist dann vorbei.
      // Ohne das hebt der Browser die Auswahl gleich wieder auf.
      setTimeout(() => quantity.select(), 0);
    });

    quantity.addEventListener("input", () => {
      // Getippten Wert übernehmen. Leeres Feld ist erlaubt – es wird für die
      // Zwischensumme als 0 gerechnet. Wichtig: kein showOrderItems() hier!
      product.quantity = parseQuantity(quantity.value);
      updateSummary();
    });

    quantity.addEventListener("change", () => {
      // Feld verlassen oder Enter: jetzt auf einen gültigen Wert bringen.
      product.quantity = Math.max(1, parseQuantity(quantity.value));
      quantity.value = product.quantity;
      updateSummary();
    });

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.textContent = "Entfernen";
    removeButton.addEventListener("click", () => {
      selectedProducts.delete(product.id);
      showOrderItems();
    });

    row.append(name, quantity, removeButton);
    orderItems.append(row);

    // Preise und MwSt. berechnen.
    totalCents += product.price_cents * product.quantity;
    totalTaxCents += calculateTax(product);
  }

  updateSummary();
}

function formatCents(cents) {
  return (cents / 100).toFixed(2).replace(".", ",");
}

function parseQuantity(raw) {
  // Liest den Feldinhalt als ganze Zahl. Leer oder ungültig -> 0.
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) {
    return 0;
  }
  return Math.floor(n);
}

function updateSummary() {
  // Berechnet nur Gesamtbetrag und MwSt. Die Liste wird NICHT angefasst.
  // Dadurch bleibt der Cursor im Eingabefeld, wo er ist.
  let totalCents = 0;
  let totalTaxCents = 0;

  for (const product of selectedProducts.values()) {
    // quantity kann während des Tippens kurz 0 sein – dann zählt die
    // Position in diesem Moment nichts.
    totalCents += product.price_cents * product.quantity;
    totalTaxCents += calculateTax(product);
  }

  totalElement.textContent = `Gesamtbetrag: ${formatCents(totalCents)} €`;
  taxElement.textContent = `MwSt.: ${formatCents(totalTaxCents)} €`;
}

orderForm.addEventListener("submit", async (event) => {
  // Nicht normal neu laden, sondern die Daten als JSON an Python schicken.
  event.preventDefault();

  const selectedFulfillment = document.querySelector('input[name="art"]:checked');
  const orderData = {
    customer_name: document.querySelector("#kundenname").value.trim(),
    delivery_address: document.querySelector("#adresse").value.trim(),
    customer_phone: document.querySelector("#telefon").value.trim(),
    order_date: document.querySelector("#datum").value,
    order_time: document.querySelector("#uhrzeit").value,
    fulfillment_type: selectedFulfillment ? selectedFulfillment.value : "",
    // Nur ID und Menge senden; Python liest den echten Preis selbst aus SQLite.
    items: [...selectedProducts.values()].map((product) => ({
      product_id: product.id,
      quantity: product.quantity,
    })),
  };

  const response = await fetch("/api/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(orderData),
  });
  const result = await response.json();

  if (!response.ok) {
    saveHint.textContent = result.error;
    return;
  }

  saveHint.textContent = `Bestellung Nr. ${result.order_id} wurde gespeichert.`;
  orderForm.reset();
  selectedProducts.clear();
  searchResults.replaceChildren();
  showOrderItems();
});
