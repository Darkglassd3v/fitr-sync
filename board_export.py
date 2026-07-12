"""
FITR Board Export
=================
Estrae la programmazione di OGGI dal primo account destinazione (coach) e la salva
in docs/board_data.json per la visualizzazione sulla board.

Ricava plan_track_id e user_id in automatico dal plan_id.
Lanciato dopo il sync nel workflow GitHub Actions.
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitr_sync import FitrClient, clean_text, load_destinations

DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)


def main():
    # Usa la prima destinazione abilitata per la board
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

    today = date.today().isoformat()
    print(f"Estraggo programmazione del {today}...")

    sections_raw = dst.get_day_sections_coach(today, plan_id, plan_track_id, user_id)

    sections = []
    for s in sorted(sections_raw, key=lambda x: x.get("position", 0)):
        attachments = []
        for att in s.get("attachments", []):
            attachments.append({
                "title": clean_text(att.get("title", "") or ""),
                "kind":  att.get("kind", ""),
                "src":   att.get("src", ""),
            })
        sections.append({
            "title":       clean_text(s.get("title", "") or ""),
            "description": clean_text(s.get("description", "") or ""),
            "attachments": attachments,
        })

    weekdays = ["Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato", "Domenica"]
    months = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
              "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    dt = datetime.strptime(today, "%Y-%m-%d")
    date_label = f"{weekdays[dt.weekday()]} {dt.day} {months[dt.month]}"

    output = {
        "date":         today,
        "date_label":   date_label,
        "generated_at": datetime.now().isoformat(),
        "sections":     sections,
        "empty":        len(sections) == 0,
    }

    out_path = DOCS_DIR / "board_data.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Salvato: {out_path} ({len(sections)} sezioni)")


if __name__ == "__main__":
    main()
