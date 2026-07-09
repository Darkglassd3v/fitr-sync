#!/bin/bash
# ============================================================
# deploy.sh — Push locale del progetto FITR su GitHub
#
# USO:
#   ./deploy.sh "messaggio del commit"
#
# Il token viene letto dalla variabile d'ambiente GITHUB_TOKEN
# oppure dal file .git-token (che NON va committato).
#
# SETUP (una volta sola):
#   echo "ghp_IL_TUO_TOKEN" > .git-token
#   chmod 600 .git-token
#   chmod +x deploy.sh
# ============================================================

set -e

REPO_USER="Darkglassd3v"
REPO_NAME="fitr-sync"

# Messaggio commit (default con data)
MSG="${1:-Aggiornamento $(date +%F_%H%M)}"

# Recupera il token
if [ -n "$GITHUB_TOKEN" ]; then
    TOKEN="$GITHUB_TOKEN"
elif [ -f ".git-token" ]; then
    TOKEN="$(cat .git-token)"
else
    echo "ERRORE: token non trovato."
    echo "Crea il file .git-token con dentro il tuo token, oppure esporta GITHUB_TOKEN."
    exit 1
fi

# Imposta remote con token (temporaneo, non salvato nella config)
REMOTE="https://${REPO_USER}:${TOKEN}@github.com/${REPO_USER}/${REPO_NAME}.git"

echo "Commit: $MSG"
git add -A
git commit -m "$MSG" || { echo "Niente da committare."; exit 0; }
git push "$REMOTE" HEAD:main

echo "Fatto."
