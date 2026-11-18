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
  // Büfett: Startmenge = Personenzahl, sonst 1.
  quantity.value = String(product.bundle_persons || 1);
  quantity.dataset.alt = quantity.value;

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

  // Büfett: Bestandteile als eigene Zeilen anhängen und bei einer
  // Änderung der Personenzahl mitskalieren.
  if (product.components) {
    for (const part of product.components) {
      addPartRow(product, part);
    }
    quantity.addEventListener("change", () => {
      scaleParts(quantity, `#neue-positionen input[data-bundle-id="${product.id}"]`);
    });
  }

  syncCheckboxes();
  updatePlaceholder();
}

function addPartRow(bundle, part) {
  const row = document.createElement("div");
  row.className = "bestellposition";
  row.dataset.bundleId = bundle.id;   // bewusst KEIN data-product-id

  const name = document.createElement("span");
  name.textContent = `↳ ${part.name} (im Büfett enthalten)`;

  const quantity = document.createElement("input");
  quantity.type = "number";
  quantity.min = "1";
  quantity.value = String(part.quantity);
  quantity.dataset.perPerson = part.per_person;
  quantity.dataset.bundleId = bundle.id;
  // Name, den Python ausliest: neu_teil_<büfett-id>_<produkt-id>
  quantity.name = `neu_teil_${bundle.id}_${part.id}`;

  quantity.addEventListener("focus", () => {
    setTimeout(() => quantity.select(), 0);
  });

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.textContent = "Entfernen";
  removeButton.addEventListener("click", () => row.remove());

  row.append(name, quantity, removeButton);
  neuePositionen.append(row);
}


function removePosition(productId) {
  // Zeile aus dem Formular entfernen.
  const row = neuePositionen.querySelector(`[data-product-id="${productId}"]`);
  if (row) {
    row.remove();
  }

  // Bestandteile dieses Büfetts (falls es eins ist) mit entfernen.
  neuePositionen
    .querySelectorAll(`div[data-bundle-id="${productId}"]`)
    .forEach((teil) => teil.remove());

  added.delete(productId);
  syncCheckboxes();
  updatePlaceholder();
}

function scaleParts(bundleInput, partSelector) {
  // Personenzahl hat sich geändert: jeden Bestandteil um die Differenz
  // verschieben, damit manuelle Abweichungen erhalten bleiben.
  const alt = parseInt(bundleInput.dataset.alt, 10);
  const neu = parseInt(bundleInput.value, 10);

  // Leer oder 0: nichts skalieren. 0 löscht das Büfett beim Speichern
  // samt Bestandteilen (macht der Server).
  if (Number.isNaN(neu) || neu < 1) {
    return;
  }

  const diff = neu - alt;
  document.querySelectorAll(partSelector).forEach((teil) => {
    const menge = parseInt(teil.value, 10);
    // Leere oder auf 0 gesetzte Bestandteile nicht wiederbeleben.
    if (!(menge > 0)) {
      return;
    }
    // Stück pro Person kann ein Dezimalwert sein (z. B. 1,5).
    const perPerson = parseFloat(teil.dataset.perPerson) || 1;
    teil.value = Math.max(1, Math.round(menge + diff * perPerson));
  });

  bundleInput.dataset.alt = String(neu);
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

// Bereits gespeicherte Zeilen: Büfett erkennen und Bestandteile mitskalieren.
document.querySelectorAll("input[data-alt][data-product-id]").forEach((input) => {
  input.addEventListener("change", () => {
    const selector = `input[data-bundle-id="${input.dataset.productId}"]`;

    if (document.querySelector(selector)) {
      scaleParts(input, selector);       // Büfett: Bestandteile anpassen
    } else if (input.value !== "") {
      input.dataset.alt = input.value;   // normale Zeile: nur merken
    }
  });
});