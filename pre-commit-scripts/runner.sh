#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PIDS=()
SCRIPTS=()
OUTPUTS=()

echo "Starting parallel execution of pre commit checks..."

for script in "$SCRIPT_DIR"/*.sh; do
    if [ -x "$script" ] && [ "$(basename "$script")" != "runner.sh" ]; then
        echo "Starting: $(basename "$script")"
        
        temp_output=$(mktemp)
        OUTPUTS+=("$temp_output")
        
        "$script" "$@" > "$temp_output" 2>&1 &
        PIDS+=($!)
        SCRIPTS+=("$script")
    fi
done

FAILED=0
for i in "${!PIDS[@]}"; do
    if ! wait "${PIDS[$i]}"; then
        echo "❌ Failed: $(basename "${SCRIPTS[$i]}")"
        echo "Error output:"
        echo "----------------------------------------"
        cat "${OUTPUTS[$i]}"
        echo "----------------------------------------"
        echo ""
        FAILED=1
    else
        echo "✅ Success: $(basename "${SCRIPTS[$i]}")"
        # Show non-empty stdout on success too — a hook may print a short
        # summary line that devs need to see. The ``-s`` guard means scripts
        # that print nothing stay silent, so this doesn't add noise for
        # check-only scripts.
        [ -s "${OUTPUTS[$i]}" ] && cat "${OUTPUTS[$i]}"
    fi
    
    rm -f "${OUTPUTS[$i]}"
done

if [ $FAILED -eq 1 ]; then
    echo "Some security checks failed!"
    exit 1
else
    echo "All security checks passed!"
    exit 0
fi
