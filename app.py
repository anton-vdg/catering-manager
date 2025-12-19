import datetime as dt
from pathlib import Path
import streamlit as st
import db
import invoice_pdf

# -------------------- Seiteneinstellungen --------------------
st.set_page_config(
    page_title="Partyservice – Bestellungen",
    layout="wide"
)

# -------------------- Datenbank initialisieren --------------------
db.init_db()

# -------------------- Anzeige-Texte --------------------
STATUS_LABELS = {
    "open": "Offen",
    "paid": "Bezahlt",
}

ZAHLUNGSARTEN = ["", "cash", "card", "transfer"]

ZAHLUNGSART_LABELS = {
    "": "—",
    "cash": "Bar",
    "card": "Karte",
    "transfer": "Überweisung",
}

ART_LABELS = {
    "pickup": "Abholung",
    "delivery": "Lieferung",
}

MWST_OPTIONEN = [
    ("19 %", 0.19),
    ("7 %", 0.07),
]

# -------------------- Hilfsfunktionen --------------------
def euro_zu_cent(betrag_euro: float) -> int:
    """Wandelt Euro (float) in Cent (int) um"""
    return int(round(float(betrag_euro) * 100))


def cent_zu_euro_text(cent: int) -> str:
    """Formatiert Cent als Euro-Text (deutsch)"""
    return f"{cent / 100:.2f}".replace(".", ",")


# -------------------- Titel --------------------
st.title("Partyservice – Bestellverwaltung")

tab_bestellung, tab_tagesliste, tab_produkte = st.tabs(
    ["Neue Bestellung", "Tagesliste", "Produktliste"]
)

# ==========================================================
# TAB 1: Neue Bestellung
# ==========================================================
with tab_bestellung:
    st.subheader("Neue Bestellung anlegen")

    linke_spalte, rechte_spalte = st.columns(2)

    # -------- Termin & Art --------
    with linke_spalte:
        event_date = st.date_input(
            "Datum", 
            value=dt.date.today(), format="DD.MM.YYYY"
        )
        
        event_time = st.time_input(
            "Uhrzeit (Abholung / Lieferung)",
            value=dt.datetime.now().time().replace(second=0, microsecond=0)
        )

        fulfilment_type = st.selectbox(
            "Art",
            options=list(ART_LABELS.keys()),
            format_func=lambda k: ART_LABELS[k]
        )

        notes = st.text_area(
            "Notizen",
            placeholder="z. B. Allergien, extra Besteck, Klingeln bei ..."
        )

    # -------- Kundendaten --------
    with rechte_spalte:
        customer_name = st.text_input(
            "Name",
        )

        customer_phone = st.text_input(
            "Telefon",
        )

        customer_address = st.text_area(
            "Adresse",
        )

    # -------- Auftragsebene --------
    st.markdown("---")
    st.markdown("**Auftragsebene**")

    c1, c2 = st.columns(2)
    with c1:
        delivery_fee_eur = st.number_input(
            "Lieferpauschale (EUR, brutto)",
            min_value=0.0,
            step=1.0,
            value=0.0
        )

    with c2:
        discount_eur = st.number_input(
            "Rabatt (EUR, brutto)",
            min_value=0.0,
            step=1.0,
            value=0.0
        )

    # -------- Produkte --------
    st.markdown("---")
    st.markdown("**Produkte**")

    if "items" not in st.session_state:
        st.session_state["items"] = [{
            "product_id": None,
            "description": "",
            "quantity": 1.0,
            "unit": "Stk",
            "unit_price_eur": 0.0,
            "vat_rate": 0.19
        }]

    def position_hinzufuegen():
        st.session_state["items"].append({
            "product_id": None,
            "description": "",
            "quantity": 1.0,
            "unit": "Stk",
            "unit_price_eur": 0.0,
            "vat_rate": 0.19
        })

    def letzte_position_entfernen():
        if len(st.session_state["items"]) > 1:
            st.session_state["items"].pop()

    b1, b2 = st.columns(2)
    with b1:
        st.button("Position hinzufügen", on_click=position_hinzufuegen)
    with b2:
        st.button("Letzte Position entfernen", on_click=letzte_position_entfernen)

    produkte = db.list_products(active_only=True)
    produkte_by_id = {p["id"]: p for p in produkte}

    def produkt_text(p: dict) -> str:
        return p["name"]

    optionen = [None] + [p["id"] for p in produkte]

    for i, item in enumerate(st.session_state["items"]):
        # Einheit als eigenes Feld anzeigen
        c_prod, c_desc, c_qty, c_unit, c_price, c_vat = st.columns([3, 6, 2, 2, 3, 2])

        try:
            idx = optionen.index(item.get("product_id"))
        except ValueError:
            idx = 0

        pid = c_prod.selectbox(
            "Produkt",
            options=optionen,
            index=idx,
            format_func=lambda x: "— (Freitext)" if x is None else produkt_text(produkte_by_id[x]),
            key=f"prod_{i}",
        )

        # Produktwechsel: alles vorbelegen (Menge+Einheit+Preis+MwSt)
        if pid != item.get("product_id"):
            item["product_id"] = pid
            if pid is not None:
                p = produkte_by_id[pid]

                item["description"] = p["name"]
                st.session_state[f"desc_{i}"] = p["name"]

                std_qty = float(p.get("default_quantity", 1.0))
                item["quantity"] = std_qty
                st.session_state[f"qty_{i}"] = std_qty

                std_unit = (p.get("default_unit") or "Stk").strip() or "Stk"
                item["unit"] = std_unit
                st.session_state[f"unit_{i}"] = std_unit

                item["unit_price_eur"] = float(p["default_unit_price_cents"]) / 100.0
                st.session_state[f"price_{i}"] = item["unit_price_eur"]

                item["vat_rate"] = float(p["default_vat_rate"])

        item["description"] = c_desc.text_input(
            "Beschreibung",
            value=st.session_state.get(f"desc_{i}", item.get("description", "")),
            key=f"desc_{i}",
        )

        item["quantity"] = c_qty.number_input(
            f"Menge #{i+1}",
            value=float(st.session_state.get(f"qty_{i}", item.get("quantity", 1.0))),
            min_value=0.0,
            step=1.0,
            key=f"qty_{i}",
        )

        item["unit"] = c_unit.text_input(
            "Einheit",
            value=st.session_state.get(f"unit_{i}", item.get("unit", "Stk")),
            key=f"unit_{i}",
        )

        item["unit_price_eur"] = c_price.number_input(
            f"Einzelpreis (EUR, brutto) #{i+1}",
            value=float(st.session_state.get(f"price_{i}", item.get("unit_price_eur", 0.0))),
            min_value=0.0,
            step=0.5,
            key=f"price_{i}",
        )

        vat_values = [x[1] for x in MWST_OPTIONEN]
        try:
            vat_idx = vat_values.index(float(item.get("vat_rate", 0.19)))
        except ValueError:
            vat_idx = 0

        auswahl = c_vat.selectbox(
            f"MwSt #{i+1}",
            options=list(range(len(MWST_OPTIONEN))),
            format_func=lambda x: MWST_OPTIONEN[x][0],
            index=vat_idx,
            key=f"vat_{i}",
        )
        item["vat_rate"] = MWST_OPTIONEN[auswahl][1]

    # -------- Gesamtsumme Vorschau --------
    st.markdown("---")

    gesamt_cent = 0
    for it in st.session_state["items"]:
        desc = (it.get("description") or "").strip()
        if not desc:
            continue
        preis_cent = euro_zu_cent(float(it.get("unit_price_eur", 0.0)))
        menge = float(it.get("quantity", 0.0) or 0.0)
        gesamt_cent += int(round(preis_cent * menge))

    gesamt_cent += euro_zu_cent(delivery_fee_eur)
    gesamt_cent -= euro_zu_cent(discount_eur)

    st.write(
        f"**Vorschau Gesamtbetrag (brutto): "
        f"{cent_zu_euro_text(gesamt_cent)} €**"
    )

    # -------- Speichern --------
    if st.button("Bestellung speichern", type="primary"):
        try:
            kunden_id = None
            if customer_name.strip() or customer_phone.strip():
                kunden_id = db.upsert_customer(
                    name=customer_name.strip() or "Unbekannt",
                    phone=customer_phone,
                    address=customer_address
                )

            positionen = []
            for it in st.session_state["items"]:
                desc = (it.get("description") or "").strip()
                if not desc:
                    continue

                positionen.append({
                    "product_id": it.get("product_id"),
                    "description": desc,
                    "quantity": float(it.get("quantity", 1.0)),
                    "unit": (it.get("unit") or "Stk").strip() or "Stk",
                    "unit_price_cents": euro_zu_cent(float(it.get("unit_price_eur", 0.0))),
                    "vat_rate": float(it.get("vat_rate", 0.19)),
                })

            if not positionen:
                raise ValueError("Mindestens eine Position ist erforderlich.")

            order_id = db.create_order(
                customer_id=kunden_id,
                event_date=event_date.isoformat(),
                event_time=event_time.strftime("%H:%M"),
                fulfilment_type=fulfilment_type,
                notes=notes,
                discount_cents=euro_zu_cent(discount_eur),
                delivery_fee_cents=euro_zu_cent(delivery_fee_eur),
                items=positionen
            )

            st.success(f"Bestellung gespeichert (Nr. {order_id})")
            st.session_state["items"] = [{
                "description": "",
                "quantity": 1.0,
                "unit_price_eur": 0.0,
                "vat_rate": 0.19
            }]
            st.rerun()

        except Exception as e:
            st.error(f"Fehler: {e}")


# ==========================================================
# TAB 2: Tagesliste / Rechnungen
# ==========================================================
with tab_tagesliste:
    st.subheader("Tagesliste / Rechnungen")

    col1, col2 = st.columns([1, 1])
    with col1:
        start_tag = st.date_input(
            "Von",
            value=dt.date.today(),
            key="start_tag"
        )

    with col2:
        end_tag = st.date_input(
            "Bis",
            value=dt.date.today(),
            key="end_tag"
        )

    orders = db.list_orders_for_period(start_tag.isoformat(), end_tag.isoformat())

    if not orders:
        st.info("Keine Bestellungen für diesen Tag.")
    else:
        for o in orders:
            order_id = int(o["id"])

            titel = (
                f"#{order_id} – {o['event_time']} – "
                f"{ART_LABELS.get(o['fulfilment_type'], o['fulfilment_type'])} – "
                f"{STATUS_LABELS.get(o['status'], o['status'])}"
            )
            if o.get("customer_name"):
                titel += f" – {o['customer_name']}"
            if o.get("invoice_number"):
                titel += f" – Rechnung {o['invoice_number']}"

            with st.expander(titel, expanded=False):
                links, rechts = st.columns([3, 2])

                # -------------------- Linke Seite: Details --------------------
                with links:
                    st.write("**Kunde**")
                    st.write(f"Name: {o.get('customer_name') or '-'}")
                    st.write(f"Telefon: {o.get('customer_phone') or '-'}")
                    if o["fulfilment_type"] == "delivery":
                        st.write(f"Adresse: {o.get('customer_address') or '-'}")

                    if o.get("notes"):
                        st.write("**Notizen**")
                        st.write(o["notes"])

                    st.write("**Positionen**")
                    items = db.get_order_items(order_id)
                    for it in items:
                        line_gross = int(round(float(it["quantity"]) * int(it["unit_price_cents"])))
                        einheit = (it.get("unit") or "").strip()
                        einheit_txt = f" {einheit}" if einheit else ""
                        st.write(
                            f"- {float(it['quantity']):g}{einheit_txt} × {it['description']} "
                            f"({cent_zu_euro_text(int(it['unit_price_cents']))} €; MwSt {int(float(it['vat_rate'])*100)}%) "
                            f"= **{cent_zu_euro_text(line_gross)} €**"
                        )

                    totals = db.compute_totals(order_id)
                    st.markdown("---")
                    st.write(f"Lieferpauschale: {cent_zu_euro_text(totals['delivery_fee_cents'])} €")
                    st.write(f"Rabatt: -{cent_zu_euro_text(totals['discount_cents'])} €")
                    st.write(f"**Gesamt (Brutto): {cent_zu_euro_text(totals['gross_total_cents'])} €**")

                    st.write("**MwSt-Aufschlüsselung**")
                    for vat_rate, vals in sorted(totals["by_vat"].items(), key=lambda x: x[0]):
                        st.write(
                            f"- {int(vat_rate*100)}%: Netto {cent_zu_euro_text(vals['net'])} € / "
                            f"MwSt {cent_zu_euro_text(vals['vat'])} € / "
                            f"Brutto {cent_zu_euro_text(vals['gross'])} €"
                        )

                # -------------------- Rechte Seite: Status, Zahlung, Rechnung --------------------
                with rechts:
                    st.write("**Status / Zahlung / Rechnung**")

                    neuer_status = st.selectbox(
                        "Auftragsstatus",
                        options=list(STATUS_LABELS.keys()),
                        index=list(STATUS_LABELS.keys()).index(o["status"]),
                        format_func=lambda k: STATUS_LABELS[k],
                        key=f"status_{order_id}",
                    )

                    aktuelle_art = o.get("payment_method") or ""
                    if aktuelle_art not in ZAHLUNGSARTEN:
                        ZAHLUNGSARTEN.append(aktuelle_art)

                    zahl_art = st.selectbox(
                        "Zahlungsart",
                        options=ZAHLUNGSARTEN,
                        index=ZAHLUNGSARTEN.index(aktuelle_art),
                        format_func=lambda k: ZAHLUNGSART_LABELS.get(k, k),
                        key=f"paymethod_{order_id}",
                    )

                    s1, s2 = st.columns(2)
                    with s1:
                        if st.button("Status speichern", key=f"save_status_{order_id}"):
                            try:
                                db.update_status(order_id, neuer_status)
                                st.success("Auftragsstatus aktualisiert")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Fehler: {e}")

                    with s2:
                        if st.button("Zahlung speichern", key=f"save_pay_{order_id}"):
                            try:
                                db.set_payment_method(order_id, zahl_art)   # nur Zahlungsart speichern
                                db.update_status(order_id, "paid")          # Auftrag auf bezahlt setzen
                                st.success("Zahlung gespeichert und Auftrag auf 'Bezahlt' gesetzt")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Fehler: {e}")


                    st.markdown("---")

                    if not o.get("invoice_number"):
                        if st.button("Rechnungsnummer vergeben", key=f"assign_inv_{order_id}"):
                            try:
                                inv = db.assign_invoice_number(order_id)
                                st.success(f"Rechnung vergeben: {inv}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Fehler: {e}")
                    else:
                        st.write(f"Rechnungsnummer: **{o['invoice_number']}**")
                        st.write(f"Rechnungsdatum: **{o.get('invoice_date') or '-'}**")

                    if st.button("Rechnung als PDF erzeugen", key=f"pdf_{order_id}"):
                        try:
                            # Falls du invoice_pdf.py deutsch benannt hast:
                            if hasattr(invoice_pdf, "rechnung_pdf_erzeugen"):
                                pdf_path = invoice_pdf.rechnung_pdf_erzeugen(order_id)
                            else:
                                # Falls noch alte Funktion:
                                pdf_path = invoice_pdf.generate_invoice_pdf(order_id)

                            st.success(f"PDF erstellt: {pdf_path}")

                            pdf_bytes = Path(pdf_path).read_bytes()
                            st.download_button(
                                label="PDF herunterladen",
                                data=pdf_bytes,
                                file_name=Path(pdf_path).name,
                                mime="application/pdf",
                                key=f"dl_{order_id}",
                            )
                        except Exception as e:
                            st.error(f"Fehler: {e}")

                    st.markdown("---")
                    st.write("**Bestellung löschen**")

                    bestaetigen = st.checkbox(
                        "Ich möchte diese Bestellung endgültig löschen",
                        key=f"del_confirm_{order_id}",
                    )

                    if st.button("Bestellung löschen", key=f"del_btn_{order_id}", disabled=not bestaetigen):
                        try:
                            db.delete_order(order_id)
                            st.success("Bestellung wurde gelöscht.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Fehler: {e}")


# ==========================================================
# TAB 3: Produktliste
# ==========================================================

with tab_produkte:

    col1, col2 = st.columns(2)
    with col1:
        pname = st.text_input("Produktname")
        pprice = st.number_input("Standardpreis (EUR, brutto)", min_value=0.0, step=0.5, value=0.0)
    with col2:
        pqty = st.number_input("Standardmenge", min_value=0.0, step=1.0, value=1.0)
        punit = st.text_input("Einheit (z.B. Stk, Portion, kg)", value="Stk")
        pvat = st.selectbox("Standard-MwSt", options=[0.19, 0.07], format_func=lambda x: f"{int(x*100)} %")
        psku = st.text_input("Artikelnummer (optional)")

    if st.button("Produkt speichern"):
        pid = db.create_product(
            name=pname,
            default_unit_price_cents=int(round(pprice * 100)),
            default_vat_rate=float(pvat),
            default_unit=punit,
            default_quantity=float(pqty),
            sku=psku or None,
        )
        st.success(f"Produkt angelegt (ID {pid})")

    st.markdown("---")
    produkte = db.list_products(active_only=False)
    st.write("**Produkte**")
    for p in produkte:
        st.write(
            f"- [{p['id']}] {p['name']} | {p.get('default_quantity', 1)} {p['default_unit']} | "
            f"{p['default_unit_price_cents']/100:.2f} € | MwSt {int(p['default_vat_rate']*100)}% | Aktiv: {bool(p['is_active'])}"
        )

