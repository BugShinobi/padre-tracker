#!/bin/bash
set -e

SERVER="cokle@100.111.164.86"
REMOTE_DIR="/home/cokle/padre-tracker"

echo "==> Syncing code..."
rsync -av --exclude='.venv' --exclude='data' --exclude='logs' --exclude='.git' \
  "$(dirname "$0")/" "$SERVER:$REMOTE_DIR/"

echo "==> Restarting services..."
ssh "$SERVER" "sudo systemctl restart padre-tracker padre-dashboard"

echo "==> Status..."
ssh "$SERVER" "systemctl is-active padre-tracker padre-dashboard"

echo "==> Done."
