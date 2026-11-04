# Hugo: Betriebsdokumentation für Proxmox-Deployment

**Version:** 0.4.0  
**Zielumgebung:** Debian VM unter Proxmox mit Docker & Docker Compose  
**Letztes Update:** 4. November 2026

---

## Übersicht

Hugo ist ein proaktiver persönlicher Assistent basierend auf:
- **FastAPI** Web-Server (HTTP REST API + Server-gerendertes Web-UI)
- **PostgreSQL 17** mit pgvector-Extension
- **Background-Worker** (tägliche proaktive Auswertung via APScheduler)
- **OpenAI API** (gpt-5-mini als zentrale LLM)

Die Produktionskonfiguration trennt die Web-Anwendung vom Background-Worker und läuft beide aus einem Image.

---

## Voraussetzungen auf der Debian-VM

### System
- Debian 12 oder Ubuntu 24.04 LTS
- ca. 4 GB RAM (8 GB für komfortablen Betrieb)
- 20 GB Festplatte (10 GB für OS, 10 GB für Datenbank)
- Stabile Internetverbindung (für OpenAI API)

### Software
```bash
# Docker & Docker Compose installieren (als root)
curl -fsSL https://get.docker.com | sh
usermod -aG docker debian  # Nutzer der docker-Gruppe hinzufügen

# Ggf. Docker Compose updaten (kommt mit Docker ≥ 20.10)
docker compose version  # Sollte 2.20+ sein
```

### Netzwerk
- Hugo wird standardmäßig unter `127.0.0.1:8000` gebunden (nur lokal)
- Für externe Erreichbarkeit: nginx Reverse-Proxy aufsetzen (siehe unten)
- Ausgehende Verbindungen zu `api.openai.com` müssen erlaubt sein

---

## 1. Installation auf einer neuen VM

### 1.1 Repository klonen

```bash
cd /opt  # oder anderes Produktionsverzeichnis
git clone https://github.com/jhohmann/hugo.git
cd hugo
```

### 1.2 Umgebungsdatei erstellen

```bash
# Kopiere die Template-Datei
cp .env.prod.template .env.prod

# Editiere .env.prod und trage ein:
# 1. Sicheres DB_PASSWORD (z.B. `openssl rand -base64 32`)
# 2. OpenAI API-Key
# 3. Optional: WEB_PORT, SCHEDULER_HOUR, LOG_LEVEL

vim .env.prod  # oder nano .env.prod
```

**Wichtig:** `.env.prod` enthält Secrets und darf NICHT in Git commitet werden.  
(`.gitignore` ist bereits konfiguriert.)

### 1.3 Docker-Image bauen

```bash
# Baue das Hugo-Backend-Image (einmalig oder vor Updates)
docker compose -f compose.prod.yaml build
```

Das Image ist ~800 MB groß und enthält Python 3.12 + alle Dependencies.

### 1.4 Services starten (erste Installation)

```bash
# Starte alle Services: db, web, worker
docker compose -f compose.prod.yaml --env-file .env.prod up -d

# Überprüfe Status
docker compose -f compose.prod.yaml ps
```

**Erwartet:**
```
NAME                 STATUS           PORTS
hugo-db              Up (healthy)     (internal network only)
hugo-web             Up (healthy)     127.0.0.1:8000->8000/tcp
hugo-worker          Up (running)     (internal network only)
```

### 1.5 Verfügbarkeit überprüfen

```bash
# Health-Check
curl http://localhost:8000/health
# Antwortet: {"status": "ok"}

# Web-UI
# Öffne im Browser: http://localhost:8000/ui

# API (Swagger)
# http://localhost:8000/docs
```

Bei Fehlern: Logs anschauen (siehe Abschnitt 6).

---

## 2. Täglicher Betrieb

### 2.1 Status überprüfen

```bash
# Alle Services
docker compose -f compose.prod.yaml ps

# Nur Web-Server
docker ps | grep hugo-web

# Logs sehen (aktuelle 50 Zeilen)
docker compose -f compose.prod.yaml logs -n 50 web
docker compose -f compose.prod.yaml logs -n 50 worker
docker compose -f compose.prod.yaml logs -n 50 db
```

### 2.2 Neu starten

```bash
# Nur Web-Server neu starten (DB bleibt oben)
docker compose -f compose.prod.yaml restart web

# Alle Services neu starten
docker compose -f compose.prod.yaml restart

# Vollständiger Neustart (alle herunterfahren + starten)
docker compose -f compose.prod.yaml down
docker compose -f compose.prod.yaml --env-file .env.prod up -d
```

### 2.3 Logs verfolgen (Live)

```bash
# Alle Logs, kontinuierlich
docker compose -f compose.prod.yaml logs -f

# Nur Web-Server, kontinuierlich
docker compose -f compose.prod.yaml logs -f web

# Nur Worker, kontinuierlich
docker compose -f compose.prod.yaml logs -f worker
```

### 2.4 Manuell Proaktivität auswerten

Der Worker läuft täglich um 06:00 UTC.  
Um manuell zu evaluieren:

```bash
# HTTP Request an den Web-Server
curl -X POST http://localhost:8000/proactivity/evaluate

# Oder in der Web-UI: "Heute" → "Jetzt auswerten" Button
```

---

## 3. Updates und Upgrades

### 3.1 Backend-Code aktualisieren

```bash
cd /opt/hugo

# Pull latest code
git pull origin main

# Rebuild Docker-Image (neue Dependencies, Code-Änderungen)
docker compose -f compose.prod.yaml build

# Restart services (webund worker nutzen neues Image)
docker compose -f compose.prod.yaml down
docker compose -f compose.prod.yaml --env-file .env.prod up -d

# Verifiziere
docker compose -f compose.prod.yaml ps
```

### 3.2 Datenbankmigrationen

Migrationen werden **automatisch beim Container-Start** ausgeführt:
1. Der `db` Container startet und führt SQL-Dateien in `/docker-entrypoint-initdb.d/` aus
2. Eine `schema_version` Tabelle tracked bereits angewendete Migrationen
3. Neue Migrationen werden nur einmal pro Datenbank ausgeführt

**Wichtig:** Vor Migrationen sollte ein Backup existieren (siehe Abschnitt 4).

---

## 4. Backup und Restore

### 4.1 Backup durchführen

**Manuell (ad-hoc):**

```bash
# In das Produktionsverzeichnis wechseln
cd /opt/hugo

# DB-Dump erstellen
docker exec hugo-db pg_dump -U hugo -d hugo > backup_$(date +%Y%m%d_%H%M%S).sql

# Größe prüfen
ls -lh backup_*.sql
```

**Automatisiert (täglich via Cron):**

```bash
# Crontab öffnen
crontab -e

# Füge folgende Zeile ein (täglich um 02:00 Uhr):
0 2 * * * cd /opt/hugo && docker exec hugo-db pg_dump -U hugo -d hugo > backup_$(date +\%Y\%m\%d).sql && find . -name 'backup_*.sql' -mtime +7 -delete
```

Dies erstellt täglich ein Backup und löscht Dateien älter als 7 Tage.

### 4.2 Restore durchführen

**Wenn die Datenbank beschädigt ist:**

```bash
# Services stoppen
docker compose -f compose.prod.yaml down

# Volume löschen (WARNUNG: Löscht alle Daten!)
docker volume rm hugo_postgres_data

# Services erneut starten (DB wird mit schema.sql + migrations neu initialisiert)
docker compose -f compose.prod.yaml --env-file .env.prod up -d

# Optionell: Konversationen/Memories aus Backup importieren
# (Datenbank startet leer, Schema ist da, aber keine Daten)
docker exec -i hugo-db psql -U hugo -d hugo < backup_20261104_120000.sql
```

---

## 5. Externe Erreichbarkeit (Reverse-Proxy)

Hugo läuft standardmäßig nur unter `127.0.0.1:8000` (lokal).  
Für externe Erreichbarkeit braucht man einen **Reverse-Proxy** (z.B. nginx).

### 5.1 nginx als Reverse-Proxy

**nginx installieren:**

```bash
apt-get update && apt-get install -y nginx
```

**nginx konfigurieren:**

Erstelle `/etc/nginx/sites-available/hugo`:

```nginx
server {
    listen 80;
    server_name hugo.example.com;  # Domain anpassen

    # Redirect HTTP → HTTPS (optional, wenn Zertifikat vorhanden)
    # return 301 https://$server_name$request_uri;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }

    # Websocket-Unterstützung (falls später nötig)
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**Aktiviere die Config:**

```bash
ln -s /etc/nginx/sites-available/hugo /etc/nginx/sites-enabled/
nginx -t  # Syntax überprüfen
systemctl restart nginx
```

**Optional: SSL mit Let's Encrypt:**

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d hugo.example.com
```

---

## 6. Troubleshooting

### 6.1 Services starten nicht

```bash
# Logs ansehen
docker compose -f compose.prod.yaml logs db web worker

# Häufige Fehler:
# - DATABASE_URL ist falsch → .env.prod überprüfen
# - OPENAI_API_KEY fehlt → openai.com/api-keys
# - Port 8000 ist bereits in Benutzung → WEB_PORT in .env.prod ändern
```

### 6.2 Web-Server antwortet nicht

```bash
# Health-Check
curl http://localhost:8000/health
# Falls 000: Verbindung abgelehnt

# Logs
docker compose -f compose.prod.yaml logs -f web

# Neu starten
docker compose -f compose.prod.yaml restart web

# Im extremsten Fall
docker compose -f compose.prod.yaml down
docker compose -f compose.prod.yaml --env-file .env.prod up -d
```

### 6.3 Worker führt Evaluation nicht aus

```bash
# Worker Logs (suche nach "scheduled evaluation")
docker compose -f compose.prod.yaml logs -f worker

# Prüfe Scheduler-Zeit (SCHEDULER_HOUR in .env.prod)
grep SCHEDULER .env.prod

# Manuell triggern (sollte direkt antworten)
curl -X POST http://localhost:8000/proactivity/evaluate
```

### 6.4 Datenbank ist voll oder langsam

```bash
# Größe überprüfen
docker exec hugo-db du -sh /var/lib/postgresql/data

# Wenn > 5 GB und wenig Inhalt:
# Backup erstellen, Volume löschen, wiederherstellen (siehe Abschnitt 4.2)

# Ggf. Vacuum ausführen (Defragmentierung)
docker exec hugo-db vacuumdb -U hugo -d hugo
```

### 6.5 Alte Logs verwalten

Docker Compose speichert Logs im `json-file` Format.  
Diese können groß werden; die Konfiguration limitiert bereits auf 10-50 MB pro Service.

Falls manuell aufräumen nötig:
```bash
# Alle Docker-Logs prüfen
du -sh /var/lib/docker/containers/*/

# Logs für einen spezifischen Container löschen
docker exec hugo-web truncate -s 0 /var/lib/docker/containers/*/\*-json.log

# Oder: systemweit aufräumen (WARNUNG: löscht Logs aller Container)
docker system prune --all --volumes  # Nur, wenn sicher!
```

---

## 7. Monitoring und Alarmierung

### 7.1 Einfaches Monitoring (manuell)

```bash
# Status täglich überprüfen
docker compose -f compose.prod.yaml ps

# Fehler letzte 24h anschauen
docker compose -f compose.prod.yaml logs --since 24h | grep ERROR
```

### 7.2 E-Mail-Alarmierung (optional)

Wenn ein Service ausfällt, kann `systemd` eine E-Mail schicken.  
Dies ist für spätere Versionen geplant.

---

## 8. Sicherheitshinweise

⚠️ **Hugo ist aktuell für vertrauenswürdige Netzwerke ausgelegt (keine Authentifizierung).**

### 8.1 Netzwerk-Isolation

```bash
# Nur aus dem lokalen Netzwerk erreichbar (Firewall)
# oder: Hinter einem Reverse-Proxy mit HTTP-Auth

# UFW Firewall (Debian/Ubuntu):
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (nginx)
ufw allow 443/tcp   # HTTPS (nginx)
ufw enable
```

### 8.2 Secrets-Verwaltung

- `.env.prod` ist `.gitignore` und darf NICHT öffentlich sein
- DB-Passwort mindestens 32 Zeichen (randomisiert)
- OpenAI API-Key hat Quotas → monitoring empfohlen

```bash
# Berechtigungen setzen
chmod 600 .env.prod

# Nur für Nutzer "hugo" lesbar (wenn Systemnutzer)
chown hugo:hugo .env.prod
```

### 8.3 Backup-Sicherheit

Backups enthalten potenziell sensitive Daten.  
- Lokal speichern (nicht in öffentliche Cloud ohne Verschlüsselung)
- Regelmäßig auf Umfang prüfen

---

## 9. Support und Weitere Hilfe

- **GitHub Issues:** https://github.com/jhohmann/hugo/issues
- **Dokumentation:** [AGENTS.md](./AGENTS.md), [README.md](./README.md)
- **API Dokumentation:** Nach dem Start unter `/docs` (Swagger)

---

## 10. Häufig gestellte Fragen

### F: Kann ich Hugo auf mehreren VMs laufen lassen?

A: Aktuell ist es auf eine einzelne Instanz ausgelegt. Eine verteilte Setup (Load-Balancer, replizierte DB) ist nicht getestet.

### F: Wie viel kostet die OpenAI API?

A: Das kommt auf die Nutzung an. Mit `gpt-5-mini` und einer Auswertung täglich sollte es unter 1 USD/Monat sein. Monitor auf https://platform.openai.com/account/billing/usage.

### F: Können Erinnerungen und Threads exportiert werden?

A: Ja, über die API:
```bash
curl http://localhost:8000/memories?limit=1000 | jq > memories_export.json
curl http://localhost:8000/threads?limit=1000 | jq > threads_export.json
```

### F: Wie funktioniert die proaktive Auswertung?

A: Der `worker` Container läuft täglich zur konfigurierten Zeit und ruft `run_evaluation(trigger='scheduled')` auf.  
Dies liest aktive Threads, Memories und erzeugt Suggestions, die im Web-UI unter "Heute" sichtbar sind.

### F: Ich bin in der EU. Ist OpenAI GDPR-konform?

A: OpenAI hat Datenschutzrichtlinien. Hugo sollte keine sensiblen persönlichen Daten enthalten, die nicht auch lokal gespeichert sind.  
Für kritische Daten: prüfe OpenAI ToS und lokale Datenschutzbestimmungen.

---

**Ende der Dokumentation**  
Version 0.4.0 | 4. November 2026
