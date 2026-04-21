#!/bin/bash
# Deploy: push locally, then pull + restart on server.
# Server is a git repo aligned with origin/main — no rsync needed.
# sudo systemctl restart prompts for password once (use -t to forward TTY).

set -e

SERVER="cokle@100.111.164.86"
REMOTE_DIR="/home/cokle/padre-tracker"

echo "==> Pushing local commits..."
git push origin main

echo "==> Pulling on server + restart..."
ssh -t "$SERVER" "cd $REMOTE_DIR && \
  git pull origin main --ff-only && \
  .venv/bin/pip install -r requirements.txt -q && \
  sudo systemctl restart padre-tracker padre-dashboard && \
  echo '--- status ---' && \
  systemctl is-active padre-tracker padre-dashboard"

echo "==> Done."
