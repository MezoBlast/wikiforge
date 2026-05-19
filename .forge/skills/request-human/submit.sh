#!/bin/sh
# submit.sh — append a structured request to .forge/requests/inbox/<id>.md
#
# Usage:
#   submit.sh --agent A --type T --urgency U --title "..." [--key K] < body
#
# Body comes from stdin and should contain the four sections:
#   ## What I need
#   ## Why
#   ## If granted
#   ## If denied
#
# Dedup: if --key is given and an open request (inbox without matching response)
# already exists with the same (type, key), exits 3 without creating a new file.
set -eu

agent=""; type=""; urgency=""; title=""; key=""
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) sed -n '2,/^set -eu/p' "$0" | sed 's/^# //'; exit 0 ;;
        --agent)   agent="${2:?--agent requires value}"; shift 2 ;;
        --type)    type="${2:?--type requires value}"; shift 2 ;;
        --urgency) urgency="${2:?--urgency requires value}"; shift 2 ;;
        --title)   title="${2:?--title requires value}"; shift 2 ;;
        --key)     key="${2:?--key requires value}"; shift 2 ;;
        *) echo "submit.sh: unknown arg: $1" >&2; exit 2 ;;
    esac
done

[ -n "$agent" ] && [ -n "$type" ] && [ -n "$urgency" ] && [ -n "$title" ] \
    || { echo "submit.sh: --agent, --type, --urgency, --title all required" >&2; exit 2; }

case "$urgency" in
    blocking|useful|nice-to-have) ;;
    *) echo "submit.sh: urgency must be one of: blocking, useful, nice-to-have" >&2; exit 2 ;;
esac

WORKSPACE="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
inbox="$WORKSPACE/.forge/requests/inbox"
responses="$WORKSPACE/.forge/requests/responses"
[ -d "$inbox" ] || { echo "submit.sh: no inbox at $inbox" >&2; exit 1; }

# dedup: scan inbox; skip any whose response exists
if [ -n "$key" ]; then
    for f in "$inbox"/*.md; do
        [ -f "$f" ] || continue
        existing_id=$(basename "$f" .md)
        [ -f "$responses/$existing_id.md" ] && continue  # already responded; not "open"
        existing_type=$(awk '/^type: / { sub(/^type: */, ""); print; exit }' "$f")
        existing_key=$(awk '/^key: / { sub(/^key: */, ""); print; exit }' "$f")
        if [ "$existing_type" = "$type" ] && [ "$existing_key" = "$key" ]; then
            echo "submit.sh: open request already exists with type=$type key=$key (id=$existing_id)" >&2
            exit 3
        fi
    done
fi

today=$(date -u +%Y-%m-%d)
seq=1
while [ -e "$inbox/$today-$(printf '%03d' "$seq").md" ]; do
    seq=$((seq + 1))
done
id="$today-$(printf '%03d' "$seq")"
out="$inbox/$id.md"

body=$(cat)
[ -n "$body" ] || body='## What I need

<TODO>

## Why

<TODO>

## If granted

<TODO>

## If denied

<TODO>
'

{
    echo '---'
    echo "id: $id"
    echo "agent: $agent"
    echo "type: $type"
    echo "urgency: $urgency"
    echo "created: $today"
    [ -n "$key" ] && echo "key: $key"
    echo "title: \"$title\""
    echo '---'
    echo
    echo "$body"
} > "$out"

# log
log="$WORKSPACE/.forge/log.md"
[ -f "$log" ] && printf '\n## [%sT00:00:00Z] request-human | submitted %s (%s, %s)\n\n%s\n' \
    "$today" "$id" "$urgency" "$type" "$title" >> "$log"

# notify on blocking
if [ "$urgency" = "blocking" ]; then
    notify="$WORKSPACE/.forge/skills/request-human/notify.sh"
    if [ -x "$notify" ]; then
        URGENCY="$urgency" REQUEST_ID="$id" TITLE="$title" "$notify" || true
    fi
fi

echo "$out"
