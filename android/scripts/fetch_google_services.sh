#!/usr/bin/env bash
# Regenerates the gitignored android/app/google-services.json from Firebase.
# Requires the Firebase CLI to be logged in (`firebase login`) as an account
# with access to the notification-relay-73586 project.
set -euo pipefail

cd "$(dirname "$0")/.."

FIREBASE_APP_ID="1:574093998225:android:98b1ffae77725ba434e730"
PROJECT_ID="notification-relay-73586"

firebase apps:sdkconfig ANDROID "$FIREBASE_APP_ID" \
  --project "$PROJECT_ID" \
  --out app/google-services.json

echo "Wrote android/app/google-services.json"
