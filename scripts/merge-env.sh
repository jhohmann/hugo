#!/usr/bin/env bash
# Ergänzt fehlende Schlüssel aus .env.prod.template in .env.prod.
# Bestehende Werte bleiben unverändert; Secrets müssen nicht neu kopiert werden.
# Aufruf auf dem Docker-Host: bash scripts/merge-env.sh
set -euo pipefail
cd "$(dirname "$0")/.."

template=".env.prod.template"
target=".env.prod"

if [[ ! -f "$template" ]]; then
    echo "Vorlage $template fehlt." >&2
    exit 1
fi

if [[ ! -f "$target" ]]; then
    cp "$template" "$target"
    chmod 600 "$target"
    echo "$target neu aus Vorlage erstellt. Bitte Werte eintragen."
    exit 0
fi

added=0
while IFS= read -r line || [[ -n "$line" ]]; do
    # Nur unkommentierte KEY=...-Zeilen berücksichtigen.
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    key="${key//[[:space:]]/}"
    [[ -z "$key" ]] && continue
    if ! grep -qE "^[[:space:]]*${key}=" "$target"; then
        printf '%s\n' "$line" >> "$target"
        echo "Ergänzt: $key"
        added=$((added + 1))
    fi
done < "$template"

if [[ $added -eq 0 ]]; then
    echo "Keine neuen Schlüssel; $target ist aktuell."
else
    echo "$added Schlüssel ergänzt. Bitte neue Werte in $target prüfen."
fi
