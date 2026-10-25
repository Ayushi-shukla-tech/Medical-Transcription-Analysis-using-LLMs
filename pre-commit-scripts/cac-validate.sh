#!/bin/bash

name="$(git rev-parse --show-toplevel 2>/dev/null | xargs basename 2>/dev/null || echo '')"
name_lc=$(echo "$name" | tr '[:upper:]' '[:lower:]')

CAC_API_URL="https://observe.meeshogcp.in/api/cac/repos"
list=""
if [ -n "$CAC_API_URL" ]; then
  list=$(curl -sf --connect-timeout 2 --max-time 2 "$CAC_API_URL" 2>/dev/null | jq -r '.repos[]? // empty' 2>/dev/null | tr -d '\r')
  if [ $? -ne 0 ] || [ -z "$list" ]; then
    echo "⏭️  CAC allowlist API unavailable, skipping validation"
    exit 0
  fi
fi

found=0
if [ -n "$name_lc" ] && [ -n "$list" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        [[ -z "$line" ]] && continue
        line_trimmed=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        line_lc=$(echo "$line_trimmed" | tr '[:upper:]' '[:lower:]')
        if [ "$name_lc" = "$line_lc" ]; then
            found=1
            break
        fi
    done <<< "$list"
fi

if [ "$found" -eq 0 ]; then
    echo "⏭️  Repository validation skipped ($name not in allowlist)"
    exit 0
fi

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [[ "$branch" == hotfix_* ]]; then
    echo "⏭️  Validation skipped for branch type"
    exit 0
fi

staged=$(git diff --cached --name-only 2>/dev/null | grep -E '^configs?/' | head -1)
if [ -z "$staged" ]; then
    echo "⏭️  No relevant changes detected"
    exit 0
fi

echo "🔍 Running CAC (Config as Code) schema validation..."
output=$(cac validate 2>&1)
code=$?

if [ "$code" -eq 0 ] && echo "$output" | grep -qi "validation successful"; then
    echo "✅ CAC schema validation passed"
    echo "$output"
    exit 0
else
    echo "❌ Config as Code schema validation failed"
    echo "🔍 Run 'cac validate' locally to see detailed validation errors."
    echo "$output"
    echo "If you need assistance, contact @abhinandan.virmani or the on-call"
    exit 1
fi