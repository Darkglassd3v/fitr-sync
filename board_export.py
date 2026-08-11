"""
FITR Board Export
=================
Estrae la programmazione della SETTIMANA CORRENTE dal primo account
destinazione abilitato e la salva in docs/board_data.json per la board.

Lanciato dopo il sync nel workflow GitHub Actions.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitr_sync import FitrClient, clean_text, load_destinations

DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)

WEEKDAYS_SHORT = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
WEEKDAYS_LONG  = ["Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato", "Domenica"]
MONTHS = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
          "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def extract_sections(raw_sections):
    out = []
    for s in sorted(raw_sections, key=lambda x: x.get("position", 0)):
        attachments = []
        for att in s.get("attachments", []):
            attachments.append({
                "title": clean_text(att.get("title", "") or ""),
                "kind":  att.get("kind", ""),
                "src":   att.get("src", ""),
            })
        out.append({
            "title":       clean_text(s.get("title", "") or ""),
            "description": clean_text(s.get("description", "") or ""),
            "attachments": attachments,
        })
    return out


def main():
    dest = None
    for d in load_destinations():
        if d.get("enabled", False) and d.get("email") and d.get("password"):
            dest = d
            break

    if not dest:
        print("Nessuna destinazione abilitata con credenziali per la board.")
        sys.exit(1)

    dst = FitrClient("BOARD")
    if not dst.login(dest["email"], dest["password"]):
        sys.exit(1)

    plan_id       = dest["plan_id"]
    plan_track_id = dest["plan_track_id"]
    user_id       = dest["user_id"]
    if not plan_track_id or not user_id:
        print(f"Parametri piano mancanti per '{dest['label']}'.")
        sys.exit(1)

    # Settimana corrente: lunedi -> domenica
    today  = date.today()
    monday = today - timedelta(days=today.weekday())

    print(f"Estraggo settimana {monday} -> {monday + timedelta(days=6)}")

    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        d_iso = d.isoformat()
        try:
            raw = dst.get_day_sections_coach(d_iso, plan_id, plan_track_id, user_id)
        except Exception as ex:
            print(f"  {d_iso}: errore ({ex}), lo tratto come vuoto")
            raw = []

        sections = extract_sections(raw)
        days.append({
            "date":        d_iso,
            "weekday":     WEEKDAYS_SHORT[i],
            "day_number":  d.day,
            "date_label":  f"{WEEKDAYS_LONG[i]} {d.day} {MONTHS[d.month]}",
            "is_today":    d == today,
            "sections":    sections,
            "empty":       len(sections) == 0,
        })
        print(f"  {d_iso} ({WEEKDAYS_SHORT[i]}): {len(sections)} sezioni")

    output = {
        "week_start":   monday.isoformat(),
        "week_end":     (monday + timedelta(days=6)).isoformat(),
        "today":        today.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "days":         days,
    }

    out_path = DOCS_DIR / "board_data.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(d["sections"]) for d in days)
    print(f"Salvato: {out_path} ({total} sezioni totali sulla settimana)")


if __name__ == "__main__":
    main()
