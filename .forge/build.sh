#!/usr/bin/env bash
# build.sh — wikiforge bundle builder (thin wrapper around .forge/lib/build.py)
set -eu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
exec python3 "$SCRIPT_DIR/lib/build.py" --workspace "$WORKSPACE" "$@"
