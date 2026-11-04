// Verifica la suddivisione in gruppi delle descrizioni della board.
// Esecuzione: node --test tests/board_lv_gruppi.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const docs = path.join(__dirname, "..", "docs");
const html = fs.readFileSync(path.join(docs, "board_v2.html"), "utf8");
const inizio = html.indexOf("// ═══ Livelli e carichi");
const fine = html.indexOf("// Evidenze dentro il testo");
assert.ok(inizio > 0 && fine > inizio, "blocco dei livelli non trovato in board_v2.html");
const { lvGruppi, lvChiave, LV_SOLO } = new Function(
  html.slice(inizio, fine) + "; return { lvGruppi, lvChiave, LV_SOLO };")();

// Riduce ogni gruppo alla forma [prima riga, marcatore, livello ereditato].
const forma = desc => lvGruppi(desc).map(g => [g.righe[0].trim(), g.lv, g.segue || null]);

// Testo reale del blocco S1: RELATIVE STRENGTH (GYM.) del 2026-11-03, accorciato.
const MARTEDI = `(Relative) Strength / Gymnastics, Press and Pull

Elite: 
a. 4 sets, 2 min AMRAP / 1:30 min Rest 
Max Strict HSPU in the remaining time

b. 4 sets, 2 min AMRAP / 1:30 min Rest
Max Legless Rope-Climbs in the remaining time

RX1: 
a. 4 sets, 2 min AMRAP / 1:30 min Rest
Max Strict HSPU in the remaining time

b. 4 sets, 2 min AMRAP / 1:30 min Rest
Max Legless Rope-Climbs in the remaining time

RX2: 
a. 4 rounds:
1 min AMRAP: Strict HSPU

b. 4 rounds:
1 min AMRAP: Rope-Climbs 

Intermediate: 
(Option 1)
a. 4 rounds:
1 min AMRAP: Kipping HSPU

b. 4 rounds:
1 min AMRAP: Rope-Climbs 

(Option 2)
Spend 20 min going through KHSPU and /or Rope-climb progressions.
----------------------------------
Read more about how gymnastics is developed in our program.`;

test("RX1 e RX2 sono marcatori di livello della famiglia RX", () => {
  for (const riga of ["RX1:", "RX2: ", "Rx1", "RX 2", "[RX1]", "Elite + RX1:"])
    assert.ok(LV_SOLO.test(riga), riga);
  assert.equal(lvChiave("RX1:"), "rx");
  assert.equal(lvChiave("RX2:"), "rx");
});

test("una riga di testo che comincia con RX1 non e' un marcatore", () => {
  for (const riga of ["RX1 athletes go heavier", "RX2 rounds", "Elite athletes often scale"])
    assert.ok(!LV_SOLO.test(riga), riga);
});

test("il blocco di martedi' assegna ogni parte al proprio livello", () => {
  assert.deepEqual(forma(MARTEDI), [
    ["(Relative) Strength / Gymnastics, Press and Pull", false, null],
    ["Elite:", true, null],
    ["b. 4 sets, 2 min AMRAP / 1:30 min Rest", false, "Elite:"],
    ["RX1:", true, null],
    ["b. 4 sets, 2 min AMRAP / 1:30 min Rest", false, "RX1:"],
    ["RX2:", true, null],
    ["b. 4 rounds:", false, "RX2:"],
    ["Intermediate:", true, null],
    ["b. 4 rounds:", false, "Intermediate:"],
    ["(Option 2)", false, "Intermediate:"],
    ["----------------------------------", false, null],
  ]);
});

test("fra due marcatori il livello continua anche sulle note", () => {
  const g = forma("Elite\n5 reps\n\nNote: keep moving\n\nRX\n3 reps");
  assert.deepEqual(g[1], ["Note: keep moving", false, "Elite"]);
});

test("il testo comune dopo l'ultimo marcatore resta fuori dal livello", () => {
  for (const coda of ["Score: Time.", "Intensity: RPE 9", "Flow explained: (Elite example)",
                      "Tempo: Quality and control is key.", "Read more in the attached document."]) {
    const g = forma(`Elite\n5 reps\n\nRX\n3 reps\n\n${coda}`);
    assert.deepEqual(g[g.length - 1], [coda, false, null]);
  }
});

test("una volta uscito dal livello non ci rientra", () => {
  const g = forma("Elite\n5 reps\n\nScore: Time.\n\nb. 3 rounds");
  assert.deepEqual(g[2], ["b. 3 rounds", false, null]);
});

test("dopo l'ultimo marcatore continuano solo le forme di workout note", () => {
  for (const riga of ["b. 4 rounds:", "(Option #2)", "(Option 2)", "- 2 minutes rest-",
                      "- 3 min rest-", "3 rounds of:", "1 round of:", "10 min EMOM",
                      "21-15-9 reps of:"]) {
    const g = forma(`Elite\n5 reps\n\n${riga}`);
    assert.deepEqual(g[1], [riga, false, "Elite"]);
  }
});

test("un solo livello con testo comune non si estende", () => {
  assert.deepEqual(forma("Elite\n5 reps\n\nScore: Time."), [
    ["Elite", true, null],
    ["Score: Time.", false, null],
  ]);
});

test("Progression e il separatore chiudono il livello anche senza riga vuota", () => {
  for (const riga of ["Progression:", "-----"]) {
    const g = lvGruppi(`Elite\n5 reps\n${riga}\nW1: 3 sets`);
    assert.equal(g.length, 2);
    assert.deepEqual(g[1].righe, [riga, "W1: 3 sets"]);
    assert.equal(g[1].lv, false);
    assert.ok(!g[1].segue);
    assert.equal(g[1].attaccato, true);
  }
});

test("il separatore chiude il livello ma il marcatore successivo lo riapre", () => {
  const g = forma("Elite\n5 reps\n-----\nRX\n3 reps\n\nb. 2 rounds");
  assert.deepEqual(g.map(x => x[2]), [null, null, null, "RX"]);
  assert.equal(g[2][1], true);
});

test("l'inizio di una fase interrompe il livello", () => {
  const g = forma("Elite\n5 reps\n\na. Warm-Up\n10 reps\n\nb. Main set\n5 rounds\n\nRX\n3 reps");
  assert.ok(g.slice(1, 3).every(x => x[2] === null));
});

test("senza marcatori nessun gruppo eredita un livello", () => {
  assert.ok(forma("a. 3 rounds\n\nb. 2 rounds\n\nScore: Time.").every(x => x[2] === null));
  assert.deepEqual(lvGruppi(""), []);
  assert.deepEqual(lvGruppi(null), []);
});

test("nessuna riga della settimana pubblicata va persa o riordinata", () => {
  const dati = JSON.parse(fs.readFileSync(path.join(docs, "board_data.json"), "utf8"));
  for (const giorno of dati.days) for (const s of giorno.sections || []) {
    const atteso = String(s.description || "").split("\n").filter(l => l.trim());
    const reso = lvGruppi(s.description).flatMap(g => g.righe).filter(l => l.trim());
    assert.deepEqual(reso, atteso, s.title);
  }
});
