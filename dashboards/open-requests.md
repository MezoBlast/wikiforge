# Open requests

Requests an agent has submitted to `.forge/requests/inbox/` that have no matching response in `.forge/requests/responses/`. These are waiting on you, the human curator.

> **Requires:** Dataview plugin with JavaScript queries enabled (Dataview settings → "Enable JavaScript Queries"). This dashboard reads `.forge/requests/` directly via Obsidian's vault adapter, bypassing the index-exclusion for that folder.

```dataviewjs
const inboxDir = ".forge/requests/inbox";
const responsesDir = ".forge/requests/responses";

const inbox = await app.vault.adapter.list(inboxDir);
const responses = await app.vault.adapter.list(responsesDir);
const respIds = new Set(
    responses.files.map(f => f.split("/").pop().replace(".md", ""))
);

const rows = [];
for (const f of inbox.files) {
    if (!f.endsWith(".md")) continue;
    const id = f.split("/").pop().replace(".md", "");
    if (respIds.has(id)) continue;
    const text = await app.vault.adapter.read(f);
    const m = text.match(/^---\n([\s\S]*?)\n---/);
    const fm = {};
    if (m) {
        for (const line of m[1].split("\n")) {
            const idx = line.indexOf(":");
            if (idx > 0) {
                const k = line.slice(0, idx).trim();
                const v = line.slice(idx + 1).trim().replace(/^"|"$/g, "");
                fm[k] = v;
            }
        }
    }
    rows.push([
        id,
        fm.urgency || "?",
        fm.type || "?",
        fm.agent || "?",
        fm.title || "(no title)",
    ]);
}

if (rows.length === 0) {
    dv.paragraph("_(no open requests)_");
} else {
    // urgency sort: blocking > useful > nice-to-have
    const order = { blocking: 0, useful: 1, "nice-to-have": 2 };
    rows.sort((a, b) => (order[a[1]] ?? 9) - (order[b[1]] ?? 9));
    dv.table(["ID", "Urgency", "Type", "Agent", "Title"], rows);
}
```

## How to respond

For each open request:

1. Read the full body: `.forge/requests/inbox/<id>.md`. The "What I need" / "Why" / "If granted" / "If denied" sections should give you everything.
2. Drop any artifacts (PDFs, credentials, etc.) into the path the request specifies.
3. Write `.forge/requests/responses/<id>.md`:

   ```yaml
   ---
   request_id: <id>
   status: granted          # or denied | deferred
   responded: YYYY-MM-DD
   artifacts:
     - raw/papers/foo.pdf
   ---
   Optional note for the agent.
   ```

4. The agent's next session picks up the response via `.forge/skills/request-human/check.sh` (run by the session-start hook) and proceeds.
5. After the agent has acted, it (or you) runs `archive.sh <id>` to move the pair into `.forge/requests/archive/<year>/`.
