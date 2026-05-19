#!/bin/sh
# notify.sh — ping the configured channel for a blocking request.
#
# Reads .forge/notify.md, extracts shell code from inside ```sh fenced blocks
# (skipping lines that begin with # — i.e., commented-out channels), and pipes
# the result into sh. The human curator uncomments the channel they want.
#
# Env vars passed through:  URGENCY, REQUEST_ID, TITLE
set -eu

WORKSPACE="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
notify="$WORKSPACE/.forge/notify.md"
[ -f "$notify" ] || { echo "notify: no $notify; skipping" >&2; exit 0; }

awk '
    /^```sh$/ || /^```$/ { in_block = !in_block; next }
    in_block && $0 !~ /^[[:space:]]*#/ { print }
' "$notify" | URGENCY="${URGENCY:-blocking}" \
              REQUEST_ID="${REQUEST_ID:-unknown}" \
              TITLE="${TITLE:-unknown}" \
              sh
