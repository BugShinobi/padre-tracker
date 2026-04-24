#!/bin/bash
# Deploy: push locally, then pull + restart on server.
# Server is a git repo aligned with origin/main.
# Passwordless sudo via /etc/sudoers.d/cokle-restart (restart only).
# Systemd unit files are NOT synced automatically — deploy warns if they drift.
# SSH still prompts for password once (ssh key setup is a TODO for full CI).

set -e

SERVER="cokle@100.111.164.86"

echo "==> Pushing local commits..."
git push origin main

echo "==> Pulling on server + restart..."
ssh -t "$SERVER" bash -s <<'REMOTE_SCRIPT'
set -e
cd /home/cokle/padre-tracker

git pull origin main --ff-only
.venv/bin/pip install -r requirements.txt -q

drift=0
for svc in padre-dashboard padre-tracker; do
  if ! diff -q "$svc.service" "/etc/systemd/system/$svc.service" >/dev/null 2>&1; then
    drift=1
    echo
    echo "!!! SYSTEMD UNIT OUT OF SYNC: $svc.service"
    echo "!!! Run manually on server:"
    echo "!!!   sudo install -m 0644 -o root -g root /home/cokle/padre-tracker/$svc.service /etc/systemd/system/"
    echo "!!!   sudo systemctl daemon-reload"
    echo "!!!   sudo systemctl restart $svc"
    echo
  fi
done

sudo systemctl restart padre-tracker padre-dashboard
echo "--- status ---"
systemctl is-active padre-tracker padre-dashboard
[ "$drift" = "1" ] && echo "WARNING: service files drifted — see messages above"
exit 0
REMOTE_SCRIPT

echo "==> Done."
