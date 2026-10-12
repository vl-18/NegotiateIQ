#!/bin/bash
# Build and deploy both React UIs to Firebase Hosting.
#
# Prerequisites:
#   npm install -g firebase-tools
#   firebase login
#   Set VITE_API_URL to the deployed Cloud Run service URL before running.
#
# Usage:
#   export VITE_API_URL=https://negotiateiq-orchestrator-xxxx-as.a.run.app/api
#   bash infra/deploy-firebase.sh

set -e

VITE_API_URL=${VITE_API_URL:?Set VITE_API_URL to your Cloud Run service URL (with /api suffix)}

echo "=== Step 1: Build buyer app (port 5173 → dist/buyer) ==="
cd ui
VITE_API_URL="$VITE_API_URL" npm run build:buyer

echo "=== Step 2: Build merchant app (port 5174 → dist/merchant) ==="
VITE_API_URL="$VITE_API_URL" npm run build:merchant
cd ..

echo "=== Step 3: Deploy both targets to Firebase Hosting ==="
firebase deploy --only hosting

echo "=== Deploy complete ==="
firebase hosting:channel:list 2>/dev/null || true
