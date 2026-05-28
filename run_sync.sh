#!/bin/bash
# run_sync.sh — wrapper per esecuzione automatica via cron o Claude Code
#
# SETUP:
#   chmod +x run_sync.sh
#
# USO DIRETTO:
#   ./run_sync.sh
#   ./run_sync.sh --override
#
# USO CON CRON (ogni lunedi alle 7:00):
#   crontab -e
#   0 7 * * 1 cd /percorso/fitr-sync && ./run_sync.sh >> fitr_sync_log/cron.log 2>&1
#
# USO CON CLAUDE CODE (headless):
#   claude -p "Esegui il sync FITR" --dangerously-skip-permissions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Carica credenziali da .env
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "ERRORE: file .env non trovato. Copia .env.example in .env e compila le credenziali."
    exit 1
fi

# Log
mkdir -p fitr_sync_log
LOG="fitr_sync_log/$(date +%Y-%m-%d_%H%M).log"

echo "=============================="  | tee -a "$LOG"
echo "FITR Sync — $(date '+%Y-%m-%d %H:%M')" | tee -a "$LOG"
echo "Argomenti: $*"                   | tee -a "$LOG"
echo "=============================="  | tee -a "$LOG"

python3 fitr_sync.py "$@" 2>&1 | tee -a "$LOG"

EXIT_CODE=${PIPESTATUS[0]}
echo ""                                | tee -a "$LOG"
echo "Completato con codice: $EXIT_CODE" | tee -a "$LOG"

exit $EXIT_CODE
