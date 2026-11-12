// =====================================================================
// order_edit.js – Produktsuche auf der Bearbeiten-Seite
//
// Eingebunden in order_edit.html:
//   <script src="/order_edit.js"></script>
//
// Aufgabe: Produkte suchen und als neue Position in die Bestellung legen.
//
// Anders als order.js wird hier NICHT per JSON gespeichert. Das Formular
// wird ganz normal abgeschickt. Damit Python die ausgewählten Produkte
// erkennt, bekommt jedes Mengenfeld den Namen "neu_menge_<produkt_id>".
// Beispiel: Produkt 5 -> <input name="neu_menge_5" value="3">
//
// In app.py liest order_bearbeiten() diese Felder aus:
//   for feldname, wert in request.form.items():
//       if feldname.startswith("neu_menge_"): ...
// =====================================================================

const searchInput = document.querySelector("#produktsuche");
const searchResults = document.querySelector("#suchergebnisse");
const neuePositionen = document.querySelector("#neue-positionen");

// Merkt sich, welche Produkte gerade hinzugefügt wurden (nur im Browser).
// Schlüssel = Produkt-ID, Wert = Produktdaten.
const added = new Map();


// ---------------------------------------------------------------------
// Suchen
// ---------------------------------------------------------------------
searchInput.addEventListener("input", async () => {
  const term = searchInput.value.trim();

  if (!term) {
    searchResults.replaceChildren();
    return;
  }

  // encodeURIComponent macht Sonderzeichen URL-sicher ("ü", "&", ...).
  const response = await fetch(
    `/api/products?query=${encodeURIComponent(term)}`
  );

  if (!response.ok) {
    searchResults.textContent = "Suche fehlgeschlagen.";
    return;
  }

  showResults(await response.json());
});


function showResults(products) {
  // Baut die Trefferliste mit je einer Checkbox pro Produkt.
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
    // Schon hinzugefügt? Dann Häkchen setzen (z. B. nach erneuter Suche).
    checkbox.checked = added.has(product.id);

    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        addPosition(product);
      } else {
        removePosition(product.id);
      }
    });

    label.append(
      checkbox,
      ` ${product.name} – ${formatCents(product.price_cents)} € pro ${product.unit}`
    );
    searchResults.append(label);
  }
}


// ---------------------------------------------------------------------
// Position hinzufügen / entfernen
// ---------------------------------------------------------------------
function addPosition(product) {
  if (added.has(product.id)) {
    return;   // schon vorhanden, nichts doppelt anlegen
  }

  const row = document.createElement("div");
  row.className = "bestellposition";
  row.dataset.productId = product.id;

  const name = document.createElement("span");
  name.textContent = `${product.name} (${formatCents(product.price_cents)} €)`;

  const quantity = document.createElement("input");
  quantity.type = "number";
  quantity.min = "1";
  quantity.value = "1";

  // DAS ist der Name, den Python ausliest.
  quantity.name = `neu_menge_${product.id}`;

  // Klick ins Feld markiert den Inhalt: "20" tippen ersetzt die 1 sofort.
  quantity.addEventListener("focus", () => {
    setTimeout(() => quantity.select(), 0);
  });

  // Entfernen darf das Formular NICHT absenden -> type="button".
  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.textContent = "Entfernen";
  removeButton.addEventListener("click", () => {
    removePosition(product.id);
  });

  row.append(name, quantity, removeButton);
  neuePositionen.append(row);

  added.set(product.id, product);
  syncCheckboxes();
  updatePlaceholder();
}


function removePosition(productId) {
  // Zeile aus dem Formular entfernen.
  const row = neuePositionen.querySelector(`[data-product-id="${productId}"]`);
  if (row) {
    row.remove();
  }

  added.delete(productId);
  syncCheckboxes();
  updatePlaceholder();
}


function syncCheckboxes() {
  // Häkchen in den Suchergebnissen an den aktuellen Zustand angleichen.
  document.querySelectorAll("#suchergebnisse [data-product-id]").forEach((checkbox) => {
    checkbox.checked = added.has(Number(checkbox.dataset.productId));
  });
}


function updatePlaceholder() {
  // Den Hinweistext ausblenden, sobald mindestens eine Zeile da ist.
  const placeholder = document.querySelector("#keine-neuen");
  if (placeholder) {
    placeholder.hidden = added.size > 0;
  }
}


function formatCents(cents) {
  // 4000 -> "40,00"
  return (cents / 100).toFixed(2).replace(".", ",");
}