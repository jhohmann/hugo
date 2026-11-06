#!/usr/bin/env bash
# Run on the Linux Docker host: bash scripts/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "Arbeitskopie enthält Änderungen. Erst committen oder separat sichern." >&2
    exit 1
fi
git pull --ff-only
compose=(docker compose --env-file .env.prod -f compose.prod.yaml)
"${compose[@]}" build web
"${compose[@]}" up -d --wait db
"${compose[@]}" stop web worker
mkdir -p backups
chmod 700 backups
umask 077
backup="backups/hugo-$(date -u +%Y%m%dT%H%M%SZ).dump"
"${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup"
echo "Backup: $backup"
# On failure the apps remain stopped; SQL rollback protects the failed migration.
"${compose[@]}" run --rm --no-deps migrate
"${compose[@]}" up -d --no-deps --wait web worker
"${compose[@]}" up -d caddy
"${compose[@]}" ps
