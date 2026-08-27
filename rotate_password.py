"""
Rotazione mensile della password della board
=============================================
La password cambia ogni mese ed e' DERIVATA da un master secret
(FITR_BOARD_SECRET) tramite HMAC-SHA256 sul periodo "YYYY-MM".

Nella pagina viene scritto SOLO l'hash PBKDF2 della password:
la password in chiaro non finisce mai nel repo, nei log, o nel sorgente.

USO (nel workflow, ad ogni deploy):
    FITR_BOARD_SECRET=... python rotate_password.py

USO (in locale, per SAPERE la password del mese corrente):
    FITR_BOARD_SECRET=... python rotate_password.py --show
"""

import hashlib
import hmac
import os
import re
import sys
from datetime import date
from pathlib import Path

MASTER = os.environ.get("FITR_BOARD_SECRET", "")

# Alfabeto senza caratteri ambigui (niente 0/O, 1/l/I)
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PWD_LEN  = 10

PBKDF2_ITERATIONS = 100_000
PAGES = ["docs/index.html", "docs/board.html", "docs/board_v2.html"]


def month_password(master: str, period: str) -> str:
    """
    Deriva la password del periodo (YYYY-MM) dal master secret.
    Deterministica: stesso secret + stesso mese = stessa password.
    """
    digest = hmac.new(master.encode(), period.encode(), hashlib.sha256).digest()
    return "".join(ALPHABET[b % len(ALPHABET)] for b in digest[:PWD_LEN])


def kiosk_token(master: str) -> str:
    """
    Token per la modalita' kiosk (TV in palestra): salta il login.
    NON dipende dal mese, cosi' la TV non va riconfigurata ogni volta.
    """
    return hmac.new(master.encode(), b"kiosk-v1", hashlib.sha256).hexdigest()[:24]


def pbkdf2_hash(password: str, salt_hex: str) -> str:
    """Hash PBKDF2-SHA256 della password, in esadecimale."""
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return dk.hex()


def main():
    if not MASTER:
        print("ERRORE: FITR_BOARD_SECRET non impostato.")
        sys.exit(1)

    period   = date.today().strftime("%Y-%m")
    password = month_password(MASTER, period)
    kiosk    = kiosk_token(MASTER)

    # --show: stampa password e link kiosk (solo in locale, MAI nel workflow)
    if "--show" in sys.argv:
        print(f"Periodo:  {period}")
        print(f"Password: {password}")
        print()
        print("Link per la TV in palestra (nessun login):")
        print(f"  board.html?kiosk={kiosk}&view=week     (v1, vista settimana)")
        print(f"  board_v2.html?kiosk={kiosk}            (v2)")
        return

    # Salt deterministico dal master secret + periodo: non serve
    # salvarlo separatamente e cambia ogni mese insieme alla password.
    salt_hex = hmac.new(
        MASTER.encode(), f"salt-{period}".encode(), hashlib.sha256
    ).hexdigest()[:32]

    pwd_hash = pbkdf2_hash(password, salt_hex)
    # Hash del token kiosk: nemmeno questo appare in chiaro nella pagina
    kiosk_hash = hashlib.sha256(("kiosk:" + kiosk).encode()).hexdigest()

    updated = 0
    for page in PAGES:
        p = Path(page)
        if not p.exists():
            continue
        html = p.read_text(encoding="utf-8")

        html, n1 = re.subn(
            r'const PWD_HASH\s*=\s*"[^"]*";',
            f'const PWD_HASH   = "{pwd_hash}";',
            html,
        )
        html, n2 = re.subn(
            r'const PWD_SALT\s*=\s*"[^"]*";',
            f'const PWD_SALT   = "{salt_hex}";',
            html,
        )
        html, n3 = re.subn(
            r'const PWD_PERIOD\s*=\s*"[^"]*";',
            f'const PWD_PERIOD = "{period}";',
            html,
        )
        html, n4 = re.subn(
            r'const KIOSK_HASH\s*=\s*"[^"]*";',
            f'const KIOSK_HASH = "{kiosk_hash}";',
            html,
        )

        if n1 and n2:
            p.write_text(html, encoding="utf-8")
            updated += 1
            print(f"  Aggiornato: {page}")
        else:
            print(f"  ATTENZIONE: segnaposto non trovati in {page}")

    # NON stampare mai la password: su repo pubblico i log sono pubblici.
    print(f"Password del periodo {period} ruotata ({updated} pagine aggiornate).")
    print("Per conoscerla: FITR_BOARD_SECRET=... python rotate_password.py --show")


if __name__ == "__main__":
    main()
