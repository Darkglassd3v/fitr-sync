"""
FITR Sync
==========
Copia tutta la programmazione disponibile dall'account A all'account B
in una singola esecuzione, partendo dal primo giorno non ancora presente su B.

SETUP:     pip install requests
USO:       python fitr_sync.py
OVERRIDE:  python fitr_sync.py --override   (ricarica anche giorni gia' presenti)
"""

import hashlib
import json
import os
import sys
import time
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

# ==============================================================
#  CONFIG
# ==============================================================

SOURCE_EMAIL    = os.environ.get("FITR_SRC_EMAIL", "")
SOURCE_PASSWORD = os.environ.get("FITR_SRC_PASS",  "")

DEST_EMAIL      = os.environ.get("FITR_DST_EMAIL", "")
DEST_PASSWORD   = os.environ.get("FITR_DST_PASS",  "")

DEST_PLAN_ID        = 371969
DEST_PLAN_TRACK_ID  = 740801
DEST_USER_ID        = 479154

# Quanti giorni in avanti scansionare su A
SCAN_DAYS = 90

# Pausa in secondi tra un giorno e l'altro (evita rate limit)
PAUSE_BETWEEN_DAYS = 2

# ==============================================================

BASE_URL      = "https://app.fitr.training"
CLIENT_ID     = "d0517fa4f15004110c85102f1fc01276ff4f3bc61b61e5c446b7c036784c03a2"
CLIENT_SECRET = "eb5c98d3a8fe0e51101a5714683d6b3009b032e96ceb4ece0198f016bdb9bc04"
OUTPUT_DIR    = Path("fitr_sync_log")
OUTPUT_DIR.mkdir(exist_ok=True)

OVERRIDE = "--override" in sys.argv


# ── Utilities ──────────────────────────────────────────────────

def ask(label, secret=False):
    if secret:
        import getpass
        return getpass.getpass(label)
    return input(label).strip()


_UNICODE_BOLD_RANGES = [
    (0x1D400, 0x41, 26), (0x1D41A, 0x61, 26),
    (0x1D434, 0x41, 26), (0x1D44E, 0x61, 26),
    (0x1D468, 0x41, 26), (0x1D482, 0x61, 26),
    (0x1D5D4, 0x41, 26), (0x1D5EE, 0x61, 26),
    (0x1D608, 0x41, 26), (0x1D622, 0x61, 26),
    (0x1D63C, 0x41, 26), (0x1D656, 0x61, 26),
    (0x1D7CE, 0x30, 10), (0x1D7D8, 0x30, 10),
    (0x1D7E2, 0x30, 10), (0x1D7EC, 0x30, 10),
]

def clean_text(text):
    result = []
    for ch in text:
        cp = ord(ch)
        mapped = None
        for base, ascii_base, length in _UNICODE_BOLD_RANGES:
            if base <= cp < base + length:
                mapped = chr(cp - base + ascii_base)
                break
        result.append(mapped if mapped else ch)
    return "".join(result)


def iso_to_display(date_iso):
    return datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def fingerprint_sections(sections: list, clean=False) -> str:
    """
    Crea un hash MD5 del contenuto delle sezioni per confrontare A vs B.
    - Usa titolo + descrizione normalizzata + numero allegati per ogni sezione
    - Se clean=True applica clean_text (per confrontare sorgente con destinazione gia' pulita)
    """
    parts = []
    for s in sorted(sections, key=lambda x: x.get("position", 0)):
        title = s.get("title", "") or ""
        desc  = s.get("description", "") or ""
        if clean:
            title = clean_text(title)
            desc  = clean_text(desc)
        # Normalizza spazi e newline
        title = " ".join(title.split())
        desc  = " ".join(desc.split())
        n_att = len(s.get("attachments", []))
        parts.append(f"{title}|{desc}|{n_att}")
    raw = "||".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def date_range_chunks(start: date, end: date, chunk=30):
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk - 1), end)
        yield cur.isoformat(), chunk_end.isoformat()
        cur = chunk_end + timedelta(days=1)


# ── FITR API Client ────────────────────────────────────────────

class FitrClient:
    def __init__(self, label=""):
        self.label   = label
        self.user_id = None
        self.session = requests.Session()
        self.session.headers.update({
            "api-version":     "3",
            "client-timezone": "Europe/Rome",
            "Accept":          "application/json",
            "Content-Type":    "application/json",
            "User-Agent":      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Origin":          "https://app.fitr.training",
            "Referer":         "https://app.fitr.training/",
        })

    def login(self, email, password):
        print(f"[{self.label}] Login come {email}...")
        resp = self.session.post(
            f"{BASE_URL}/api/users/sign_in",
            json={
                "email": email, "password": password,
                "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            }
        )
        if not resp.text.strip():
            print(f"  ERRORE: risposta vuota dal server (possibile rate limit, riprova tra qualche secondo)")
            return False
        data = resp.json()
        if resp.status_code not in (200, 201):
            print(f"  ERRORE: {data.get('base', {}).get('invalid', str(data))}")
            return False
        private = data.get("private", {})
        self.user_id = private.get("id")
        token = data.get("token") or data.get("access_token")
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        print(f"  OK: {private.get('full_name')} (id: {self.user_id})")
        return True

    # ── Sorgente ───────────────────────────────────────────────

    def get_schedule_overview(self, date_from, date_to):
        """Ritorna {date_iso: {schedule_id, sections_count, plan_title}}"""
        resp = self.session.get(
            f"{BASE_URL}/api/schedule",
            params={"from": date_from, "to": date_to}
        )
        resp.raise_for_status()
        result = {}
        for plan in resp.json().get("plans", []):
            for day in plan.get("days", []):
                d = day.get("date")
                if d:
                    result[d] = {
                        "schedule_id":    day.get("schedule_id"),
                        "sections_count": len(day.get("sections", [])),
                        "plan_title":     plan.get("title", ""),
                    }
        return result

    def get_day_detail(self, schedule_id):
        resp = self.session.get(
            f"{BASE_URL}/api/schedule/{schedule_id}/athlete/{self.user_id}"
        )
        resp.raise_for_status()
        return resp.json()

    # ── Destinazione ───────────────────────────────────────────

    def get_existing_section_ids(self, date_iso, plan_id, plan_track_id, user_id):
        """
        Controlla se il giorno ha gia' sezioni su B.
        Ritorna lista di section_id (vuota = giorno non presente o vuoto).
        """
        resp = self.session.get(
            f"{BASE_URL}/api/coach/schedules/show",
            params={
                "date": date_iso, "user_id": user_id,
                "plan_id": plan_id, "plan_track_id": plan_track_id,
            }
        )
        if resp.status_code in (404, 204):
            return []
        if not resp.text.strip():
            return []
        try:
            resp.raise_for_status()
            sections = resp.json().get("day", {}).get("sections", [])
            return [s["id"] for s in sections if s.get("id")]
        except Exception:
            return []

    def get_day_sections_coach(self, date_iso, plan_id, plan_track_id, user_id):
        """
        Ritorna le sezioni complete del giorno su B (titolo, descrizione, allegati).
        Usato per il confronto con la sorgente.
        """
        resp = self.session.get(
            f"{BASE_URL}/api/coach/schedules/show",
            params={
                "date": date_iso, "user_id": user_id,
                "plan_id": plan_id, "plan_track_id": plan_track_id,
            }
        )
        if resp.status_code in (404, 204) or not resp.text.strip():
            return []
        try:
            resp.raise_for_status()
            return resp.json().get("day", {}).get("sections", [])
        except Exception:
            return []

    def delete_sections(self, section_ids, plan_id, user_id):
        if not section_ids:
            return
        resp = self.session.delete(
            f"{BASE_URL}/api/coach/schedules/plans/{plan_id}/clients/{user_id}/remove_sections",
            json={"section_ids": section_ids, "macro_ids": []}
        )
        resp.raise_for_status()

    def register_youtube(self, youtube_url):
        resp = self.session.post(
            f"{BASE_URL}/api/media",
            json={"media": {"video_url": youtube_url}, "scope": "current"}
        )
        if resp.status_code != 200:
            print(f"    AVVISO: impossibile registrare {youtube_url}: HTTP {resp.status_code}")
            return None
        data = resp.json()
        print(f"    Video: [{data.get('id')}] {data.get('title','')}")
        return data.get("id")

    def register_pdf(self, pdf_url, title=""):
        """
        Carica un PDF sull'account destinazione in 3 step:
        1. POST /api/media/direct_upload  -> ottieni presigned S3 URL + media_id
        2. POST su S3 con il file binario
        3. GET /aws/upload_success        -> finalizza il record su FITR
        """
        # Scarica il PDF dalla CDN sorgente
        try:
            pdf_resp = requests.get(pdf_url, timeout=30)
            pdf_resp.raise_for_status()
            pdf_bytes = pdf_resp.content
        except Exception as ex:
            print(f"    AVVISO: impossibile scaricare PDF {pdf_url}: {ex}")
            return None

        filename = pdf_url.split("/")[-1].split("?")[0]
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        # Step 1: richiedi presigned URL a FITR
        upload_resp = self.session.post(
            f"{BASE_URL}/api/media/direct_upload",
            files={
                "filePath":    (None, filename),
                "contentType": (None, "application/pdf"),
            }
        )
        if upload_resp.status_code != 200:
            print(f"    AVVISO: direct_upload fallito ({upload_resp.status_code}) per {filename}")
            return None

        upload_data  = upload_resp.json()
        s3_endpoint  = upload_data.get("postEndpoint")
        signature    = upload_data.get("signature", {})
        redirect_url = signature.get("success_action_redirect", "")

        # Estrai media_id dal redirect URL (...?id=4082545&platform=web)
        media_id = None
        for part in redirect_url.split("?")[-1].split("&"):
            if part.startswith("id="):
                try:
                    media_id = int(part.split("=")[1])
                except ValueError:
                    pass

        if not media_id or not s3_endpoint:
            print(f"    AVVISO: impossibile estrarre media_id da {redirect_url}")
            return None

        # Step 2: carica su S3
        s3_fields = {k: v for k, v in signature.items()}
        s3_resp = requests.post(
            s3_endpoint,
            data=s3_fields,
            files={"file": (filename, pdf_bytes, "application/pdf")},
            allow_redirects=False,
            timeout=60,
        )
        if s3_resp.status_code not in (200, 201, 301, 302, 303):
            print(f"    AVVISO: upload S3 fallito ({s3_resp.status_code}) per {filename}")
            return None

        # Step 3: finalizza su FITR
        self.session.get(redirect_url, timeout=10)

        print(f"    PDF:   [{media_id}] {title or filename}")
        return media_id

    def create_day(self, date_iso, sections, plan_id, plan_track_id, user_id):
        sections_attrs = []
        for i, s in enumerate(sections, start=1):
            title       = clean_text(s.get("title", "") or "")
            description = clean_text(s.get("description", "") or "").strip()
            attachments = s.get("attachments", [])
            attachment_with_position = []

            for pos, att in enumerate(attachments):
                kind         = att.get("kind", "")
                att_src      = att.get("src", "")
                att_ttl      = att.get("title", "")
                video_id     = att.get("video_id", "")
                content_type = att.get("content_type", "")
                media_id     = None

                if kind == "youtube":
                    yt_url   = f"https://youtu.be/{video_id}" if video_id else att_src
                    media_id = self.register_youtube(yt_url)

                elif kind == "other" and "pdf" in content_type and att_src:
                    media_id = self.register_pdf(att_src, att_ttl)

                elif kind == "video" and att_src:
                    # Video MP4 CDN: non ricaricabile, aggiunge link in descrizione
                    description = description.rstrip() + f"\n\nVideo: {att_ttl} - {att_src}"

                if media_id:
                    attachment_with_position.append({
                        "media_id":    media_id,
                        "position":    pos,
                        "title_media": False,
                    })


            sections_attrs.append({
                "position":                i,
                "title":                   title,
                "description":             description,
                "kind":                    s.get("kind", "section"),
                "attachment_with_position": attachment_with_position,
            })

        resp = self.session.post(
            f"{BASE_URL}/api/coach/schedules/plans/{plan_id}/clients/{user_id}",
            json={
                "plan_track_id": plan_track_id,
                "day": {
                    "date":                iso_to_display(date_iso),
                    "sections_attributes": sections_attrs,
                    "macros_attributes":   None,
                }
            }
        )
        resp.raise_for_status()
        return resp.json()


# ── Main ───────────────────────────────────────────────────────

def main():
    global SOURCE_EMAIL, SOURCE_PASSWORD, DEST_EMAIL, DEST_PASSWORD

    print("=" * 55)
    print("  FITR Sync" + ("  [OVERRIDE]" if OVERRIDE else ""))
    print("=" * 55)

    if not SOURCE_EMAIL:    SOURCE_EMAIL    = ask("Email account SORGENTE: ")
    if not SOURCE_PASSWORD: SOURCE_PASSWORD = ask("Password SORGENTE: ", secret=True)
    if not DEST_EMAIL:      DEST_EMAIL      = ask("Email account DESTINAZIONE (coach): ")
    if not DEST_PASSWORD:   DEST_PASSWORD   = ask("Password DESTINAZIONE: ", secret=True)

    # Login una sola volta per tutta l'esecuzione
    print("\n-- Autenticazione --")
    src = FitrClient("SORGENTE")
    if not src.login(SOURCE_EMAIL, SOURCE_PASSWORD):
        sys.exit(1)

    dst = FitrClient("DESTINAZIONE")
    if not dst.login(DEST_EMAIL, DEST_PASSWORD):
        sys.exit(1)

    # Scarica overview sorgente (tutti i giorni disponibili su A)
    scan_start = date.today()
    scan_end   = scan_start + timedelta(days=SCAN_DAYS)
    print(f"\n-- Scan sorgente: {scan_start} → {scan_end} --")

    src_days = {}
    for chunk_from, chunk_to in date_range_chunks(scan_start, scan_end, chunk=30):
        chunk = src.get_schedule_overview(chunk_from, chunk_to)
        src_days.update(chunk)
        n = sum(1 for d in chunk.values() if d["sections_count"] > 0)
        print(f"  {chunk_from} → {chunk_to}: {n} giorni con contenuto")

    # Filtra solo giorni con contenuto, in ordine cronologico
    days_to_check = sorted(
        [(d, info) for d, info in src_days.items() if info["sections_count"] > 0]
    )

    if not days_to_check:
        print("\nNessun giorno con contenuto trovato su A.")
        sys.exit(0)

    print(f"\nTotale giorni disponibili su A: {len(days_to_check)}")
    print(f"Dal {days_to_check[0][0]} al {days_to_check[-1][0]}")

    if OVERRIDE:
        confirm = ask(f"\nOVERRIDE: ricarico tutti i {len(days_to_check)} giorni. Confermi? (s/N): ")
        if confirm.lower() != "s":
            print("Annullato.")
            sys.exit(0)

    # Loop interno: controlla ogni giorno su B e copia se mancante
    results  = []
    copied   = 0
    skipped  = 0
    errors   = 0

    print("\n-- Inizio sync --")

    for target_date, info in days_to_check:
        sched_id = info.get("schedule_id")

        # Controlla se gia' presente su B
        # Download dettaglio da A
        try:
            detail   = src.get_day_detail(sched_id)
            sections = detail.get("day", {}).get("sections", [])
        except Exception as ex:
            print(f"  {target_date}: ERRORE download — {ex}")
            errors += 1
            results.append({"date": target_date, "status": "error_download", "error": str(ex)})
            continue

        if not sections:
            print(f"  {target_date}: vuoto su A, salto.")
            continue

        n_videos = sum(
            len([a for a in s.get("attachments", []) if a.get("kind") in ("youtube", "video")])
            for s in sections
        )
        n_pdfs = sum(
            len([a for a in s.get("attachments", []) if a.get("kind") == "other"])
            for s in sections
        )

        # Controlla se gia' presente su B
        existing_ids = dst.get_existing_section_ids(
            target_date, DEST_PLAN_ID, DEST_PLAN_TRACK_ID, DEST_USER_ID
        )

        if existing_ids:
            if OVERRIDE:
                print(f"\n  {target_date}: {len(sections)} sezioni, {n_videos} video, {n_pdfs} pdf  [OVERRIDE]")
            else:
                # Confronta contenuto A vs B
                b_sections = dst.get_day_sections_coach(
                    target_date, DEST_PLAN_ID, DEST_PLAN_TRACK_ID, DEST_USER_ID
                )
                fp_a = fingerprint_sections(sections, clean=True)
                fp_b = fingerprint_sections(b_sections, clean=False)

                if fp_a == fp_b:
                    print(f"  {target_date}: identico ({len(existing_ids)} sezioni), salto.")
                    skipped += 1
                    results.append({"date": target_date, "status": "skipped_identical"})
                    continue
                else:
                    print(f"\n  {target_date}: {len(sections)} sezioni, {n_videos} video, {n_pdfs} pdf  [MODIFICATO — ricarico]")

            # Cancella sezioni esistenti (override o contenuto diverso)
            try:
                dst.delete_sections(existing_ids, DEST_PLAN_ID, DEST_USER_ID)
                print(f"    Cancellate {len(existing_ids)} sezioni esistenti.")
            except Exception as ex:
                print(f"    ERRORE cancellazione: {ex}")
                errors += 1
                results.append({"date": target_date, "status": "error_delete", "error": str(ex)})
                continue
        else:
            print(f"\n  {target_date}: {len(sections)} sezioni, {n_videos} video, {n_pdfs} pdf")

        # Upload su B
        try:
            result  = dst.create_day(
                target_date, sections,
                DEST_PLAN_ID, DEST_PLAN_TRACK_ID, DEST_USER_ID
            )
            created = len(result.get("schedule", {}).get("day", {}).get("sections", []))
            print(f"    Caricato: {created} sezioni.")
            copied += 1
            results.append({"date": target_date, "status": "ok", "sections": created})
        except Exception as ex:
            print(f"    ERRORE upload: {ex}")
            errors += 1
            results.append({"date": target_date, "status": "error_upload", "error": str(ex)})
            continue

        # Pausa tra un giorno e l'altro
        if PAUSE_BETWEEN_DAYS > 0:
            time.sleep(PAUSE_BETWEEN_DAYS)

    # Riepilogo finale
    print("\n" + "=" * 55)
    print(f"  Copiati:    {copied}")
    print(f"  Saltati:    {skipped}  (gia' presenti)")
    print(f"  Errori:     {errors}")
    if copied == 0 and skipped == len(days_to_check):
        print("\n  Tutto gia' in sync. Niente da fare.")
    print("=" * 55)

    log_path = OUTPUT_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_sync.json"
    log_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
