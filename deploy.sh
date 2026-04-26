#!/bin/bash
# Manual deploy: build frontend locally, rsync build/ to server, then pull + restart.
# Mirrors the GitHub Actions flow so the server never needs Node installed.
# Server is a git repo aligned with origin/main.
# Passwordless sudo via /etc/sudoers.d/cokle-restart (restart only).

set -e

SERVER="cokle@100.111.164.86"
REMOTE_PATH="padre-tracker"

echo "==> Pushing local commits..."
git push origin main

echo "==> Building frontend locally..."
( cd frontend && npm ci --silent && npm run build )

echo "==> Pulling on server + installing Python deps..."
ssh "$SERVER" bash -s <<'REMOTE_SCRIPT'
set -e
cd ~/padre-tracker
git pull origin main --ff-only
.venv/bin/pip install -r requirements.txt -q
REMOTE_SCRIPT

echo "==> Syncing frontend/build/ to server..."
rsync -az --delete frontend/build/ "$SERVER:$REMOTE_PATH/frontend/build/"

echo "==> Restarting services..."
ssh "$SERVER" bash -s <<'REMOTE_SCRIPT'
set -e
cd ~/padre-tracker

drift=0
for svc in padre-dashboard padre-tracker padre-workers; do
  if ! diff -q "$svc.service" "/etc/systemd/system/$svc.service" >/dev/null 2>&1; then
    drift=1
    echo
    echo "!!! SYSTEMD UNIT OUT OF SYNC: $svc.service"
    echo "!!!   sudo install -m 0644 -o root -g root $svc.service /etc/systemd/system/"
    echo "!!!   sudo systemctl daemon-reload && sudo systemctl restart $svc"
    echo
  fi
done

sudo systemctl restart padre-tracker
sudo systemctl restart padre-dashboard
if systemctl list-unit-files padre-workers.service >/dev/null 2>&1; then
  sudo systemctl restart padre-workers
else
  echo "padre-workers.service not installed yet — skip restart"
fi
echo "--- status ---"
systemctl is-active padre-tracker padre-dashboard
[ "$drift" = "1" ] && echo "WARNING: service files drifted — see messages above"
exit 0
REMOTE_SCRIPT

echo "==> Done."
