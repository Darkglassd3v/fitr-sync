"""
FITR Board Export
=================
Estrae la programmazione di OGGI dall'account B (coach) e la salva
in docs/board_data.json per la visualizzazione sulla board.

Riusa la stessa logica di login di fitr_sync.py.
Lanciato dopo il sync nel workflow GitHub Actions.
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Riusa il client dal file principale
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitr_sync import (
    FitrClient, clean_text,
    DEST_PLAN_ID, DEST_PLAN_TRACK_ID, DEST_USER_ID,
)

DEST_EMAIL    = os.environ.get("FITR_DST_EMAIL", "")
DEST_PASSWORD = os.environ.get("FITR_DST_PASS",  "")

# Cartella pubblicata su GitHub Pages
DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)


def main():
    if not DEST_EMAIL or not DEST_PASSWORD:
        print("Credenziali destinazione mancanti.")
        sys.exit(1)

    dst = FitrClient("BOARD")
    if not dst.login(DEST_EMAIL, DEST_PASSWORD):
        sys.exit(1)

    today = date.today().isoformat()
    print(f"Estraggo programmazione del {today}...")

    sections_raw = dst.get_day_sections_coach(
        today, DEST_PLAN_ID, DEST_PLAN_TRACK_ID, DEST_USER_ID
    )

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

    # Data leggibile in italiano
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
