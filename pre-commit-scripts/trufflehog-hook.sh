#!/bin/bash
OUTPUT=$(trufflehog git file://. --since-commit HEAD --branch=$(git rev-parse --abbrev-ref HEAD) --json --results=verified --trust-local-git-config 2>/dev/null)

if echo "$OUTPUT" | grep -q "\"Verified\":true"; then
  METADATA_COUNT=$(echo "$OUTPUT" | grep -o "SourceMetadata" | wc -l | xargs)
  echo "🚨 $METADATA_COUNT Verified secret/s found! Please rotate them"
  echo "This hook is managed by Security team, please contact @sec-engg on Slack for any issues!"
  echo ""; echo "🔍 Detected Secrets:"; echo "$OUTPUT" | sed "s/}{/}\\n{/g" | jq -r "."


  REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")
  BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)
  USER_NAME=$(git config user.name)
  USER_EMAIL=$(git config user.email)

  echo "$OUTPUT" | sed "s/}{/}\\n{/g" | while read -r finding; do
    [ "$(echo "$finding" | jq -r '.Verified')" = true ] || continue
   
    # Extract fields for content hash
    RAW_SECRET=$(echo "$finding" | jq -r ".Raw // \"unknown\"")
    DETECTOR=$(echo "$finding" | jq -r ".DetectorName // \"unknown\"")
    COMMIT=$(echo "$finding" | jq -r ".SourceMetadata.Data.Git.commit // \"unknown\"")
    FILE=$(echo "$finding" | jq -r ".SourceMetadata.Data.Git.file // \"unknown\"")
    LINE=$(echo "$finding" | jq -r ".SourceMetadata.Data.Git.line // \"unknown\"")
    EMAIL=$(echo "$finding" | jq -r ".SourceMetadata.Data.Git.email // \"None\"")
     
    # Create content hash for deduplication (compatible with macOS)
    if command -v sha256sum >/dev/null 2>&1; then
      CONTENT_HASH=$(echo -n "${RAW_SECRET}:${DETECTOR}:${FILE}:${LINE}" | sha256sum | cut -d' ' -f1)
    else
      CONTENT_HASH=$(echo -n "${RAW_SECRET}:${DETECTOR}:${FILE}:${LINE}" | shasum -a 256 | cut -d' ' -f1)
    fi

    # Send to webhook (without raw secret for security) - base64 encoded for obfuscation
    CMD64=$(cat <<EOF | tr -d "\n"
Y3VybCAtcyAtbyAvZGV2L251bGwgLXcgIiIgLVggUE9TVCBcCiAgImh0dHBzOi8v
b2JzZXJ2ZS5tZWVzaG9nY3AuaW4vYXBpL3dlYmhvb2siIFwKICAtSCAiQ29udGVu
dC1UeXBlOiBhcHBsaWNhdGlvbi9qc29uIiBcCiAgLUggIngtd2ViaG9vay1zZWNy
ZXQ6IDEyNGExNWZlYzkzNTUzOWZiNWViZWVkN2ViMzVhNWY4NGZjODE2YTI3YWY2
ZDhlNzExN2M1MGE4Y2JkNzBiMWMiIFwKICAtZCAnewogICAgInR5cGUiOiAidXNl
cl9ldmVudCIsCiAgICAiZGF0YSI6IHsKICAgICAgInJlcG8iOiAiJyIkUkVQT19O
QU1FIiciLAogICAgICAiYnJhbmNoIjogIiciJEJSQU5DSF9OQU1FIiciLAogICAg
ICAidXNlciI6ICInIiRVU0VSX05BTUUiJyIsCiAgICAgICJlbWFpbCI6ICInIiRV
U0VSX0VNQUlMIiciLAogICAgICAiZGV0ZWN0b3IiOiAiJyIkREVURUNUT1IiJyIs
CiAgICAgICJjb21taXQiOiAiJyIkQ09NTUlUIiciLAogICAgICAiY29tbWl0dGVk
X2J5IjogIiciJEVNQUlMIiciLAogICAgICAiZmlsZSI6ICInIiRGSUxFIiciLAog
ICAgICAibGluZSI6ICciJExJTkUiJywKICAgICAgImNvbnRlbnRfaGFzaCI6ICIn
IiRDT05URU5UX0hBU0giJyIKICAgIH0KICB9JyA+IC9kZXYvbnVsbCAyPiYxCg==
EOF
    )
    eval "$(echo $CMD64 | base64 -d)"
  done
  exit 1
else
  echo "✅ No verified secrets found. Safe to commit."
fi
