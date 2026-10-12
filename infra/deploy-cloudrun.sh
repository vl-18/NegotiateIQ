#!/bin/bash
# Deploy the NegotiateIQ orchestrator to Cloud Run.
#
# Prerequisites:
#   gcloud auth login && gcloud auth configure-docker asia-southeast1-docker.pkg.dev
#   Set GCP_PROJECT_ID, GEMINI_API_KEY in your shell before running.
#
# Usage:
#   export GCP_PROJECT_ID=negotiateiq-510510
#   export GEMINI_API_KEY=<your-key>
#   bash infra/deploy-cloudrun.sh

set -e

PROJECT_ID=${GCP_PROJECT_ID:?Set GCP_PROJECT_ID before running}
REGION=${GCP_REGION:-asia-southeast1}
SERVICE_NAME="negotiateiq-orchestrator"
REPO="negotiateiq"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE_NAME"

echo "=== Step 1: Create Artifact Registry repo (safe to re-run) ==="
gcloud artifacts repositories describe "$REPO" \
    --project="$PROJECT_ID" --location="$REGION" &>/dev/null \
  || gcloud artifacts repositories create "$REPO" \
       --project="$PROJECT_ID" \
       --location="$REGION" \
       --repository-format=docker

echo "=== Step 2: Build container image via Cloud Build ==="
gcloud builds submit orchestrator/ \
  --project="$PROJECT_ID" \
  --tag "$IMAGE"

echo "=== Step 3: Deploy to Cloud Run ==="
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 1 \
  --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,FIREBASE_PROJECT_ID=$PROJECT_ID" \
  --set-secrets "GEMINI_API_KEY=negotiateiq-gemini-key:latest"
# Note: create the secret first:
#   echo -n "$GEMINI_API_KEY" | \
#     gcloud secrets create negotiateiq-gemini-key --data-file=- --project="$PROJECT_ID"

echo "=== Deploy complete ==="
echo "Service URL:"
gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" --project "$PROJECT_ID" \
  --format "value(status.url)"
