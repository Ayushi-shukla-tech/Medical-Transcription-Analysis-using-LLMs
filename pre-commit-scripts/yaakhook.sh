#!/bin/bash

GIT_DIR="$(git rev-parse --git-dir 2>/dev/null)"

if [ -d "$GIT_DIR/rebase-merge" ] || [ -d "$GIT_DIR/rebase-apply" ]; then
    exit 0
fi

if [ -f "$GIT_DIR/CHERRY_PICK_HEAD" ] || [ -f "$GIT_DIR/REVERT_HEAD" ]; then
    exit 0
fi

echo "🔍 Running Yaak sensitive data masking..."

staged=$(git diff --cached --name-only 2>/dev/null | grep -E '^api-collections?/' | head -1)
if [ -z "$staged" ]; then
    echo "⏭️  No relevant changes detected"
    exit 0
fi

output=$(yahook api-collections 2>&1)
code=$?

if [ "$code" -eq 0 ]; then
    echo "$output"
    exit 0
else
    echo "$output"
    exit 1
fi