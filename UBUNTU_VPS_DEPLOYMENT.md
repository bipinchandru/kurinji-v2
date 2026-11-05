# KURINJI — Ubuntu VPS Production Deployment Guide

This guide walks you through deploying **KURINJI** to an **Ubuntu VPS** (Ubuntu 20.04, 22.04, or 24.04 LTS).

---

## 🏗️ Production Architecture Overview

* **Frontend**: React 19 + Vite compiled into high-performance static HTML/JS/CSS, served directly by **Nginx** with Gzip compression and 30-day audio asset caching.
* **Backend**: FastAPI + Uvicorn running on `127.0.0.1:8000`, managed 24/7 by **systemd** (`kurinji.service`) with auto-restart on crashes or server reboots.
* **Audio Caching**: Pre-cached Edge-TTS `.mp3` files and native `.wav` files served locally with **0ms latency** and zero external API fees.
* **HTTPS / SSL**: Free **Let's Encrypt (Certbot)** certificate.  
  > ⚠️ **Important for Mobile/Voice**: Modern mobile and desktop browsers strictly **block microphone access** (`getUserMedia`) over unencrypted HTTP. HTTPS is **mandatory** for speech recognition on phones and remote devices.

---

## 📋 Step-by-Step Deployment

### Step 1: Connect to Your Ubuntu VPS
Open your terminal on your local machine and SSH into your server:
```bash
ssh root@YOUR_SERVER_IP
```

---

### Step 2: Upload or Clone the Code to `/var/www/kurinji`

#### Option A: Clone via Git (Recommended)
```bash
sudo mkdir -p /var/www/kurinji
sudo chown -R $USER:$USER /var/www/kurinji
cd /var/www
git clone https://github.com/YOUR_USERNAME/KURINJI.git kurinji
cd /var/www/kurinji
```

#### Option B: Upload from your local machine via SCP/Rsync
From your local computer terminal:
```bash
rsync -avz --exclude 'node_modules' --exclude '.venv' "/home/bipin/Projects/Win Desktop Backup/KURINJI/" root@YOUR_SERVER_IP:/var/www/kurinji/
```

---

### Step 3: Run the Automated VPS Setup Script

Inside `/var/www/kurinji`, run:
```bash
chmod +x deploy_vps.sh
./deploy_vps.sh
```

**What this automated script does**:
1. Installs system packages: `python3-pip`, `python3-venv`, `nginx`, `libsndfile1` (audio), `ffmpeg`, and `Node.js 20 LTS`.
2. Creates `.venv` and installs all Python packages from `requirements.txt`.
3. Runs `warmup_tts_cache.py` to ensure all 324 curriculum Tamil and English audio clips are stored on disk.
4. Compiles the React 19 frontend into optimized production bundles in `frontend/dist/`.
5. Copies and enables `kurinji.service` under systemd so FastAPI starts automatically and runs 24/7.

---

### Step 4: Configure Nginx as the Reverse Proxy

1. Copy the provided Nginx configuration:
```bash
sudo cp /var/www/kurinji/nginx_kurinji.conf /etc/nginx/sites-available/kurinji
```

2. Enable the site and remove the default Nginx placeholder:
```bash
sudo ln -sf /etc/nginx/sites-available/kurinji /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

3. Test your Nginx configuration syntax:
```bash
sudo nginx -t
```
*(Should output: `syntax is ok / test is successful`)*

4. Reload Nginx:
```bash
sudo systemctl reload nginx
```

Now, opening `http://YOUR_SERVER_IP` in any browser will show the KURINJI interface!

---

### Step 5: Enable Free HTTPS / SSL (Mandatory for Microphone)

To enable the microphone for Badaga/Marwari speech recognition on phones, secure your server with a free SSL certificate:

1. Point your domain (e.g. `kurinji.yourdomain.com` or a free DuckDNS domain) to `YOUR_SERVER_IP` via an **A Record** in your DNS dashboard.
2. Edit `/etc/nginx/sites-available/kurinji` to replace `server_name _;` with your domain:
   ```nginx
   server_name kurinji.yourdomain.com;
   ```
   Then reload Nginx:
   ```bash
   sudo systemctl reload nginx
   ```
3. Install Certbot and generate your SSL certificate with a single command:
   ```bash
   sudo apt-get install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d kurinji.yourdomain.com
   ```
4. Follow the on-screen prompt (enter email, agree to terms). Certbot will automatically configure SSL in Nginx and schedule auto-renewals!

---

## 🛠️ Handy Maintenance & Management Commands

### Check Backend Service Status
```bash
sudo systemctl status kurinji
```

### View Live Backend Logs
```bash
sudo journalctl -u kurinji -f
```

### Restart Backend Service (e.g. after code updates)
```bash
sudo systemctl restart kurinji
```

### Update the App to a New Version
Whenever you push updates to Git, run on your VPS:
```bash
cd /var/www/kurinji
git pull
./deploy_vps.sh
sudo systemctl reload nginx
```

