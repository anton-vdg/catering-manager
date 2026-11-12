INSERT OR IGNORE INTO categories (id, name, sort_order) VALUES
  ( 1, 'Spanferkel',             10),
  ( 2, 'Braten',                 20),
  ( 3, 'Beilagen',               30),
  ( 4, 'Büfetts',                40),
  ( 5, 'Gerichte',               50),
  ( 6, 'Suppen',                 60),
  ( 7, 'Kanapees & Brötchen',    70),
  ( 8, 'Fingerfood',             80),
  ( 9, 'Vegetarisch & Vegan',    90),
  (10, 'Nachspeisen',           100),
  (11, 'Partyzubehör',          110),
  (12, 'Geflügel & Weihnachten', 120);

-- Preise in Cent (18,00 € = 1800), damit nicht mit Kommazahlen gerechnet wird.
-- tax_rate: 7 = Speisen (ermäßigt), 19 = Non-Food (voller Satz).
-- price_cents = 0 bedeutet "Preis auf Anfrage".
INSERT OR IGNORE INTO products (name, price_cents, unit, tax_rate, category_id) VALUES
  -- Spanferkel
  ('Spanferkel 10 kg (ca. 10–12 Personen)', 18000, 'Stück',  7,  1),
  ('Spanferkel 15 kg (ca. 20–25 Personen)', 23000, 'Stück',  7,  1),
  ('Spanferkel 20 kg (ca. 30–35 Personen)', 28000, 'Stück',  7,  1),
  ('Spanferkel zerlegen vor Ort',            3000, 'Stück',  7,  1),

  -- Braten
  ('Original bayerische Schweinshaxe (ca. 1,2 kg)', 1300,  'Stück', 7, 2),
  ('Lachs im Spinatblätterteig (ca. 3 kg)',        10000,  'Stück', 7, 2),
  ('Prager Schinken mit Kruste (ca. 4 kg)',         9000,  'Stück', 7, 2),
  ('Kasseler im Blätterteig (ca. 3 kg)',            7000,  'Stück', 7, 2),
  ('Truthahnbrust im Blätterteig (ca. 4 kg)',       7000,  'Stück', 7, 2),
  ('Lauchrolle (ca. 3–4 kg)',                      10000,  'Stück', 7, 2),
  ('Original bayerischer Leberkäs (2 kg)',          3000,  'Stück', 7, 2),
  ('Spießbraten (ca. 3–4 kg)',                      7000,  'Stück', 7, 2),
  ('Knuspriger Schweinebraten (ca. 4 kg)',          8000,  'Stück', 7, 2),
  ('Dicke Grillrippchen in scharfer Soße',          2000,  'Kilo',  7, 2),
  ('Ofenfrisches Brathähnchen (ganz)',              1200,  'Stück', 7, 2),

  -- Beilagen
  ('Bratkartoffeln (ab 3 kg)',   1000, 'Kilo',  7, 3),
  ('Salzkartoffeln (ab 2 kg)',   1000, 'Kilo',  7, 3),
  ('Sauerkraut (ab 2 kg)',       1000, 'Kilo',  7, 3),
  ('Rotkohl (ab 2 kg)',          1000, 'Kilo',  7, 3),
  ('Grünkohl (ab 2 kg)',         1000, 'Kilo',  7, 3),
  ('Knödel (ab 20 Stück)',        150, 'Stück', 7, 3),
  ('Bratensoße',                 1200, 'Liter', 7, 3),

  -- Büfetts
  ('Fingerfood Büfett ab 5 Personen',          2500, 'Person', 7, 4),
  ('Fingerfood Büfett ab 10 Personen',         2300, 'Person', 7, 4),
  ('Fingerfood Büfett ab 20 Personen',         2200, 'Person', 7, 4),
  ('Bayerisches Büfett ab 15 Personen',        2400, 'Person', 7, 4),
  ('Warmes und Kaltes Büfett ab 10 Personen',  2600, 'Person', 7, 4),
  ('Warmes und Kaltes Büfett ab 20 Personen',  2800, 'Person', 7, 4),
  ('Warmes und Kaltes Büfett ab 30 Personen',  2500, 'Person', 7, 4),

  -- Gerichte
  ('Currywurstpfanne (ab 3 kg)',                                     2000, 'Kilo',   7, 5),
  ('Kasseler mit Sauerkraut, Salzkartoffeln und Soße (ab 10 Pers.)', 1500, 'Person', 7, 5),
  ('Schweinebraten mit Knödel, Rotkohl und Soße',                    1500, 'Person', 7, 5),
  ('Schnitzel mit Kartoffeln, Gemüse und Soße',                      1500, 'Person', 7, 5),
  ('Rinderroulade mit Rotkohl, Kartoffeln und Soße',                 2000, 'Person', 7, 5),
  ('Rindsgulasch mit Kartoffeln, Rotkohl und Soße',                  1500, 'Person', 7, 5),
  ('Filet-Geschnetzeltes vom Huhn in Sahnesoße mit Reis',            1500, 'Person', 7, 5),
  ('Eisbein mit Sauerkraut, Kartoffeln und Erbspüree (ab 20 Pers.)', 1600, 'Person', 7, 5),

  -- Suppen
  ('Gulaschsuppe',                      1500, 'Liter', 7, 6),
  ('Chili con Carne',                   1500, 'Liter', 7, 6),
  ('Chili sin Carne (vegetarisch)',     1500, 'Liter', 7, 6),
  ('Erbsensuppe (mit oder ohne Wurst)', 1500, 'Liter', 7, 6),
  ('Tomatensuppe',                      1500, 'Liter', 7, 6),
  ('Kartoffelsuppe (vegetarisch)',      1500, 'Liter', 7, 6),

  -- Kanapees & Brötchen
  ('Kanapees gemischt (Braten, Schinken, Käse)',      250, 'Stück', 7, 7),
  ('Kanapees vegan',                                  300, 'Stück', 7, 7),
  ('Kanapees mit Fisch',                              350, 'Stück', 7, 7),
  ('Halbe belegte Brötchen gemischt',                 250, 'Stück', 7, 7),
  ('Halbe belegte Brötchen mit Fisch',                350, 'Stück', 7, 7),
  ('Schmalzbrot mit Griebenschmalz und Röstzwiebeln', 200, 'Stück', 7, 7),

  -- Fingerfood
  ('Datteln oder Pflaumen im Speckmantel (ab 10 Stk.)', 150, 'Stück',  7, 8),
  ('Garnelen auf Frischkäse und Pumpernickel',          200, 'Stück',  7, 8),
  ('Hähnchenkeulen',                                    400, 'Stück',  7, 8),
  ('Käse-Obst-Spieße',                                  150, 'Stück',  7, 8),
  ('Partybuletten',                                     150, 'Stück',  7, 8),
  ('Mini-Schnitzel vom Schwein oder Huhn',              150, 'Stück',  7, 8),
  ('Hähnchenspieße',                                    150, 'Stück',  7, 8),
  ('Tomate-Mozzarella-Spieß',                           150, 'Stück',  7, 8),
  ('1/2 Eier gefüllt',                                  150, 'Stück',  7, 8),
  ('Obstplatte (für 5 oder 10 Personen)',               600, 'Person', 7, 8),
  ('Antipastiplatte (für 5 oder 10 Personen)',          600, 'Person', 7, 8),
  ('Lachssticks',                                       200, 'Stück',  7, 8),

  -- Vegetarisch & Vegan
  ('Kartoffelgratin (3 kg)',                            4500, 'Stück', 7, 9),
  ('Gemüsegratin (3 kg)',                               4500, 'Stück', 7, 9),
  ('Nudelgratin (3 kg)',                                4500, 'Stück', 7, 9),
  ('Gemüsestrudel (ca. 350 g)',                         1000, 'Stück', 7, 9),
  ('Süßkartoffelpfanne (ab 2 kg, vegan)',               2500, 'Kilo',  7, 9),
  ('Kichererbsenpfanne (ab 2 kg, vegan)',               2500, 'Kilo',  7, 9),
  ('Ravioli-Pfifferlingspfanne (ab 2 kg, vegetarisch)', 2500, 'Kilo',  7, 9),
  ('Gnocchipfanne (ab 2 kg, vegetarisch)',              2500, 'Kilo',  7, 9),
  ('Kartoffelgulasch (ab 2 kg, vegetarisch)',           2500, 'Kilo',  7, 9),

  -- Nachspeisen
  ('Mousse au Chocolat (Schale ab 1 kg)',        1500, 'Kilo',   7, 10),
  ('Bayerische Creme (Schale ab 1 kg)',          1500, 'Kilo',   7, 10),
  ('Rote Grütze (Schale ab 1 kg)',               1500, 'Kilo',   7, 10),
  ('Vanillesoße (500 ml)',                        400, 'Stück',  7, 10),
  ('Dessert oder Obst in Weckgläsern',            400, 'Glas',   7, 10),
  ('Obstplatte (Nachspeise)',                     600, 'Person', 7, 10),
  ('Blechkuchen (Kirsch-, Apfel-, Mandelkuchen)', 300, 'Stück',  7, 10),

  -- Partyzubehör: Non-Food, daher voller Steuersatz
  ('Festzelt ohne Boden inkl. Auf- und Abbau', 1400, 'qm',     19, 11),
  ('Festzelt mit Boden inkl. Auf- und Abbau',  2000, 'qm',     19, 11),
  ('Zelt 3,00 x 4,50 Meter',                  20000, 'Stück',  19, 11),
  ('Bierzeltgarnitur',                         1500, 'Stück',  19, 11),
  ('Bistro- oder Stehtisch',                   1500, 'Stück',  19, 11),
  ('Polsterstuhl',                              700, 'Stück',  19, 11),
  ('Marktsonnenschirm 3 Meter',                4000, 'Stück',  19, 11),
  ('Terrassenheizer inkl. Gas',                8000, 'Stück',  19, 11),
  ('Gasgrill inkl. Reinigung und Gas',        10000, 'Stück',  19, 11),
  ('Glühweintopf ca. 25 Liter',                1500, 'Stück',  19, 11),
  ('Kaffeemaschine ca. 40 Tassen',             4000, 'Stück',  19, 11),
  ('Tresen mit Spüle',                        12000, 'Stück',  19, 11),
  ('Geschirr, Besteck und Gläser',               50, 'Stück',  19, 11),
  ('Service und Bedienung',                    3000, 'Stunde', 19, 11),

  -- Geflügel & Weihnachten (0 Cent = Preis auf Anfrage)
  ('Gans mit Füllung',    0, 'Stück', 7, 12),
  ('Gänsekeule',          0, 'Stück', 7, 12),
  ('Gänsebrust',          0, 'Stück', 7, 12),
  ('Ente',             4000, 'Stück', 7, 12);