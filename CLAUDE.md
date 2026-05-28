# FITR Sync — Claude Code Project

## Scopo
Scarica la programmazione settimanale dall'account Podium Chaser (sorgente)
e la carica sull'account coach FITR (destinazione).

## Struttura
```
fitr-sync/
  fitr_sync.py       # script principale
  run_sync.sh        # wrapper per esecuzione automatica
  .env               # credenziali (NON committare su git)
  CLAUDE.md          # questo file
  .claude/
    settings.json    # permessi Claude Code
  fitr_sync_log/     # log delle esecuzioni
```

## Come eseguire

### Manuale (con override)
```bash
python fitr_sync.py --override
```

### Tramite Claude Code (headless)
```bash
claude -p "Esegui il sync FITR per questa settimana" --dangerously-skip-permissions
```

### Automatico (cron — ogni lunedi alle 7:00)
```
0 7 * * 1 cd /percorso/fitr-sync && ./run_sync.sh
```

## Parametri piano destinazione (aggiorna se cambia piano)
- DEST_PLAN_ID: 371969
- DEST_PLAN_TRACK_ID: 740801
- DEST_USER_ID: 479154

## Comportamento
- Senza flag: salta giorni gia' presenti
- Con --override: svuota e ricarica tutto
- I video YouTube vengono registrati nell'account destinazione e allegati alle sezioni
- I video MP4/PDF vengono aggiunti come link in fondo alla descrizione

## In caso di errori
Controlla i log in `fitr_sync_log/`. Se il login fallisce, verifica le credenziali in `.env`.
