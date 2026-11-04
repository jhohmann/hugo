# Hugo Produktivbetrieb: Schnellstart-Checkliste

**Für Proxmox-VM Setup-Ingenieur**

---

## ✅ Vor der Installation

- [ ] Debian 12 / Ubuntu 24.04 LTS VM mit 4–8 GB RAM, 20 GB Disk
- [ ] SSH-Zugriff als `debian` oder äquivalent (sudo)
- [ ] Stabile Internetverbindung (OpenAI API)
- [ ] Domain/Subdomain (z.B. `hugo.example.com`) optional

---

## 📋 Installation (10–15 Minuten)

### 1. Systemvorbereitung

```bash
# SSH als debian, dann:
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker debian
# Logout und Login, um Docker-Gruppe zu aktivieren
docker --version  # Sollte >= 20.10 sein
```

### 2. Repository klonen

```bash
cd /opt
sudo git clone https://github.com/jhohmann/hugo.git
sudo chown -R debian:debian /opt/hugo
cd /opt/hugo
```

### 3. Secrets vorbereiten

```bash
# Kopiere Template
cp .env.prod.template .env.prod

# Generiere sichere Passwörter
DB_PASSWORD=$(openssl rand -base64 32)
echo "DB_PASSWORD=$DB_PASSWORD"  # Merken oder speichern!

# Editiere .env.prod
nano .env.prod
# Trage ein:
# - DB_PASSWORD (kopiert vom openssl-Befehl)
# - OPENAI_API_KEY (von https://platform.openai.com/api-keys)
# - Optional: WEB_PORT (default: 127.0.0.1:8000)

chmod 600 .env.prod
```

### 4. Bauen und Starten

```bash
# Image bauen (einmalig, ~3–5 Min., erster Durchlauf ~15 Min. mit Dependencies)
docker compose -f compose.prod.yaml build

# Services starten (auto-initializes DB)
docker compose -f compose.prod.yaml --env-file .env.prod up -d

# Status prüfen (warten bis alle "Up" sind)
docker compose -f compose.prod.yaml ps

# Health-Check
curl http://localhost:8000/health
# Erwartet: {"status": "ok"}
```

### 5. Web-UI öffnen

```
http://localhost:8000/ui
```

Oder über externe Domain (mit nginx, siehe unten).

---

## 🔧 Konfiguration nach Installation

### nginx Reverse-Proxy (optional, für externe Erreichbarkeit)

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Erstelle /etc/nginx/sites-available/hugo
sudo tee /etc/nginx/sites-available/hugo > /dev/null << 'EOF'
server {
    listen 80;
    server_name hugo.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 90s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/hugo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# SSL mit Let's Encrypt (optional, sehr empfohlen!)
sudo certbot --nginx -d hugo.example.com
```

### Firewall

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP (nginx)
sudo ufw allow 443/tcp  # HTTPS (nginx)
sudo ufw enable
```

---

## 📊 Tägliche Überwachung

### Status prüfen

```bash
# Alle Services laufen?
docker compose -f compose.prod.yaml ps

# Letzte Logs
docker compose -f compose.prod.yaml logs --since 1h web
```

### Sichern

```bash
# Tägliches Backup (manuell)
cd /opt/hugo
docker exec hugo-db pg_dump -U hugo -d hugo > backup_$(date +%Y%m%d).sql
ls -lh backup_*.sql

# Automatisiertes tägliches Backup (Cron)
(crontab -l 2>/dev/null; echo '0 2 * * * cd /opt/hugo && docker exec hugo-db pg_dump -U hugo -d hugo > backup_$(date +\%Y\%m\%d).sql && find . -name "backup_*.sql" -mtime +7 -delete') | crontab -
```

### Logs durchsuchen

```bash
# Fehler in den letzten 24 Stunden?
docker compose -f compose.prod.yaml logs --since 24h | grep ERROR

# Worker lädt die Evaluation täglich?
docker compose -f compose.prod.yaml logs --since 2h worker | grep "scheduled evaluation"
```

---

## 🔄 Updates

### Code aktualisieren

```bash
cd /opt/hugo
git pull origin main
docker compose -f compose.prod.yaml build
docker compose -f compose.prod.yaml down
docker compose -f compose.prod.yaml --env-file .env.prod up -d
docker compose -f compose.prod.yaml ps
```

---

## 🆘 Troubleshooting

| Problem | Lösung |
|---------|--------|
| `Services starten nicht` | `docker compose -f compose.prod.yaml logs db web worker` (Fehler? siehe unten) |
| `DB_PASSWORD nicht gesetzt` | `.env.prod` editieren und neu starten |
| `OPENAI_API_KEY ungültig` | API-Key auf https://platform.openai.com überprüfen |
| `Web antwortet nicht (Timeout)` | `docker compose -f compose.prod.yaml restart web` |
| `Worker führt Evaluation nicht aus` | `docker compose -f compose.prod.yaml logs worker` (suche "scheduled evaluation") |
| `Port 8000 ist bereits belegt` | `WEB_PORT` in `.env.prod` ändern, z.B. `8001` |
| `Disk voll` | `du -sh /var/lib/docker/` prüfen, alte Logs löschen |

---

## 📞 Support

- **Docs**: `/opt/hugo/DEPLOYMENT.md`
- **GitHub**: https://github.com/jhohmann/hugo/issues
- **API Docs**: `http://localhost:8000/docs` (Swagger)

---

## 🔐 Sicherheitshinweise

- ⚠️ `.env.prod` ist GEHEIM (enthält DB-Passwort & API-Key)
- ⚠️ Keine öffentliche DB-Erreichbarkeit (Firewall!)
- ⚠️ Hugo hat keine Authentifizierung (nur vertrauenswürdiges Netzwerk!)
- ✅ nginx + SSL verwenden für externe Erreichbarkeit
- ✅ Regelmäßige Backups (mind. täglich)

---

**Installation abgeschlossen! 🎉**

Hugo läuft jetzt unter `http://localhost:8000/ui` (lokal oder über nginx extern).
