#!/bin/sh
# archive.sh — move a resolved (request, response) pair into archive/<year>/<id>.md
#
# Combined file contains the request and response, separated by HTML-comment markers.
set -eu

id="${1:?usage: archive.sh <id>}"
WORKSPACE="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
inbox="$WORKSPACE/.forge/requests/inbox/$id.md"
resp="$WORKSPACE/.forge/requests/responses/$id.md"
[ -f "$inbox" ] || { echo "archive.sh: no inbox/$id.md" >&2; exit 1; }
[ -f "$resp" ]  || { echo "archive.sh: no responses/$id.md" >&2; exit 1; }

year=$(echo "$id" | cut -d- -f1)
arch_dir="$WORKSPACE/.forge/requests/archive/$year"
mkdir -p "$arch_dir"
out="$arch_dir/$id.md"

{
    echo "<!-- request -->"
    cat "$inbox"
    echo
    echo "<!-- response -->"
    cat "$resp"
} > "$out"

rm "$inbox" "$resp"

log="$WORKSPACE/.forge/log.md"
today=$(date -u +%Y-%m-%d)
[ -f "$log" ] && printf '\n## [%sT00:00:00Z] request-human | archived %s\n' "$today" "$id" >> "$log"

echo "$out"
