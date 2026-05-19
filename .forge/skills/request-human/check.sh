#!/bin/sh
# check.sh — list response files that haven't been archived; one line each.
#
# Output format (TSV-ish):
#   <id>\t<status>\t<title>
#
# A session-start hook should pipe this into the agent's context: "you previously
# asked for X, the human's response is Y, decide whether to resume."
set -eu

WORKSPACE="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
responses="$WORKSPACE/.forge/requests/responses"
inbox="$WORKSPACE/.forge/requests/inbox"
[ -d "$responses" ] || exit 0

any=0
for f in "$responses"/*.md; do
    [ -f "$f" ] || continue
    id=$(basename "$f" .md)
    status=$(awk '/^status: / { sub(/^status: */, ""); print; exit }' "$f")
    title=""
    [ -f "$inbox/$id.md" ] && title=$(awk '
        /^title: / { sub(/^title: */, ""); sub(/^"/, ""); sub(/"$/, ""); print; exit }
    ' "$inbox/$id.md")
    printf '%s\t%s\t%s\n' "$id" "$status" "$title"
    any=1
done

[ "$any" -eq 0 ] && echo "(no pending responses)" >&2
exit 0
