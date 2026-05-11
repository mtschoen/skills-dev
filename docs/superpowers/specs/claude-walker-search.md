# Spec — Session search (CLI subcommand + MCP shim)

Status: **DRAFT**. Once stable, the CLI section folds back into
`claude-walker/SPEC.md` under `## Subcommands`; the MCP shim graduates
to its own `SPEC-mcp.md` or stays here, depending on whether it grows
beyond search.

**Implementation hygiene.** A parallel session is actively working in
the `~/claude-walker` main checkout (the idle-exclusion port in
`PLAN.md`'s inbox). When this spec is picked up for implementation,
use a git worktree off claude-walker rather than the main checkout —
see `superpowers:using-git-worktrees`. Spec edits live here in
`skills-dev/docs/superpowers/specs/` until the spec stabilizes and
folds back into `claude-walker/SPEC.md`.

## Goal

Solve the recall problem: *"you said X a few sessions ago, but didn't
commit it to memory — go find that conversation."*

The killer characteristic is **cross-root / cross-machine** lookup. The
agent rarely thinks to check the other host's transcripts; this
subcommand inherits the existing multi-root resolution from `SPEC.md`
(`## Roots`) so a query against `chonkers` automatically reaches into
the mounted `llamabox` transcripts (and vice-versa) when configured.

Search is content-only. Identifying sessions by metadata
(timespan, cwd, tool usage) lives in a sibling `list-sessions`
subcommand spec'd separately. Keeping them split avoids overloading one
subcommand with two mental models.

## Non-goals

- **Semantic / embedding search.** Substring + regex only in v1. An
  embedding-indexed `ingest` + `search --semantic` layer is a possible
  v2, but most real "you said X" recalls have at least one memorable
  noun, and a fast substring scan over already-mtime-pruned files is
  cheap.
- **Indexing.** No on-disk index. Linear scan over surviving files,
  pinned on cores per the existing concurrency rules. The bench numbers
  (~88ms for the cost walk) leave plenty of budget for a search walk
  even with larger reads, and avoiding an index keeps the tool stateless
  and crash-proof.
- **Mutation.** Read-only. Search must NEVER write to a transcript or
  to memory.

## CLI shape

```
walker search <pattern> [flags]
```

`<pattern>` is required and positional. Empty pattern is an error.

### Flags

| Flag                          | Type   | Default     | Notes                                                                                          |
| ----------------------------- | ------ | ----------- | ---------------------------------------------------------------------------------------------- |
| `--regex`                     | bool   | false       | Treat `<pattern>` as a regex. **RE2-only syntax** (no lookaround, no backreferences) — see "Decided constraints" below. |
| `--case-sensitive`            | bool   | false       | Default is case-insensitive (the common case for recall queries).                              |
| `--role`                      | enum   | `both`      | `user`, `assistant`, `both`.                                                                   |
| `--since`                     | string | none        | RFC 3339 timestamp OR relative (`7d`, `30d`, `12h`).                                           |
| `--until`                     | string | none        | Same parsing as `--since`. Defaults to now.                                                    |
| `--cwd <slug>`                | string | none        | Restrict to one project slug (the `~/.claude/projects/<slug>` dir name).                       |
| `--any-cwd`                   | bool   | true        | Default. Explicit form for clarity when overriding `--cwd`.                                    |
| `--context <N>`               | u32    | 1           | Turns of context before AND after each hit. `0` = just the matched message; high values (e.g. `100`) give exploratory recall when the user doesn't remember exactly what they're looking for. No hard cap. |
| `--limit <N>`                 | u32    | 50          | Cap on returned hits. Soft cap — see "Overflow" below.                                         |
| `--count-only`                | bool   | false       | Emit only the summary record (no hit records). Cheap pre-flight to size a query before pulling full text. |
| `--include-tool-blocks`       | bool   | false       | If true, search inside `tool_use` and `tool_result` blocks too. Default skips them (noise).    |
| `--format`                    | enum   | `pretty`    | `pretty` (human-readable) or `jsonl` (agent-consumable; one hit per line).                     |
| `--snippet-chars <N>`         | u32    | 240         | Maximum chars in the snippet preview per hit (excluding context turns).                        |

**Root flag:** this subcommand uses the existing `--projects-root`
flag from `claude-walker/SPEC.md`'s CLI contract. No new search-specific
root flag is introduced here. Tentative future direction: rename to
`--roots` (plural, repeatable) so multiple roots can be passed
positionally without depending on `walker-roots.json` — but that
refactor is out of scope for v1 of search and should land as its own
change against the base CLI contract.

### Match semantics

A hit is a **single message** whose textual content matches the
pattern. Pseudocode:

```
for each message m in walked transcripts:
    if filter_excludes(m): continue
    text = extract_text(m)        # see "Content extraction"
    if regex_mode:
        if not pattern_regex.search(text): continue
    else:
        if pattern.casefold() not in text.casefold(): continue
    emit Hit(message=m, snippet=window_around_first_match(text))
```

### Content extraction

`message.content` is sometimes a bare string (older user-prompt
format) and sometimes a `Vec<ContentBlock>` (newer). **Strict typed
deserialization silently drops ~10% of real user prompts** — this is
the bug the Rust port already hit and the search command MUST avoid
re-hitting. Use the loose `Value` approach already proven in
`rust/src/beacons.rs`:

1. Parse `message.content` as untyped.
2. If string: that's the text.
3. If array: concatenate all `{"type": "text", "text": ...}` blocks
   with a single newline between them. With `--include-tool-blocks`,
   also concatenate `{"type": "tool_use", "input": ...}` (serialized)
   and `{"type": "tool_result", "content": ...}` blocks.
4. If neither: skip the message (treat as no text).

This same routine should be the canonical "extract textual content
from a message" helper across the codebase — `cost-mode` doesn't need
it, but if `list-sessions` lands later it will.

## Filters

Applied in this order (cheapest first):

1. **File-level mtime.** Skip files with `mtime < since_cutoff` if
   `--since` is set. Mirrors the existing cost-mode mtime prune.
2. **Slug.** If `--cwd` is set, skip files outside
   `<root>/<slug>/...`.
3. **Role.** Skip messages whose `role` doesn't match `--role`.
4. **Tool-block exclusion.** If `--include-tool-blocks` is false and
   the message's content is entirely tool blocks (no text blocks),
   skip the message. (Don't pre-skip tool_result messages just because
   `type: "user"` — the cost walk needs to see them; only the search
   walk needs to skip them, and only the all-tool-block subset.)
5. **Time window.** Skip messages with `timestamp` outside
   `[since, until]`.
6. **Pattern.** The actual match check, run last because it's the
   most expensive (regex compile is amortized; substring is fast but
   still O(text length)).

## Output

### `--format pretty` (default; for humans)

```
[2026-03-18T14:32:11Z] cwd=skills-dev role=assistant session=01HXY...
  ./root/skills-dev/01HXY-abc-def.jsonl:147
  ...one turn before the hit (truncated to 120 chars)...
  >>> the snippet, with the matched substring/regex bracketed <<<
  ...one turn after (truncated to 120 chars)...

[2026-03-15T09:10:44Z] cwd=schoen-claude-status role=user session=01HXW...
  ...

3 hits in 4 sessions across 2 roots (~/.claude/projects + /mnt/llamabox/...). elapsed 142ms.
```

### `--format jsonl` (for agents)

One JSON object per line. Final line is a summary record.

Hit record:

```json
{
  "type": "hit",
  "session_id": "01HXY...",
  "cwd_slug": "skills-dev",
  "host_root": "/mnt/llamabox/Users/schoen/.claude/projects",
  "file_path": "/mnt/.../01HXY-abc-def.jsonl",
  "line_number": 147,
  "timestamp": "2026-03-18T14:32:11Z",
  "role": "assistant",
  "snippet": "...the matched text with ±snippet_chars/2 around the first match...",
  "match_offsets": [[123, 134]],
  "context_before": [{"role": "user", "text": "...", "timestamp": "..."}],
  "context_after":  [{"role": "user", "text": "...", "timestamp": "..."}]
}
```

`host_root` is the **killer field** — it tells the agent which
machine's mount the session came from, closing the "agent didn't think
to check the other host" gap.

Summary record (always last):

```json
{"type": "summary", "hits": 3, "sessions_matched": 4, "roots_walked": 2, "files_walked": 218, "truncated": false, "elapsed_ms": 142}
```

If `--limit` was hit, `truncated: true` and the agent knows to narrow
the query (or paginate — see "Overflow").

### `--count-only` mode

When `--count-only` is set, pretty mode emits only the trailing summary
line (no per-hit blocks); jsonl mode emits only the summary record (no
hit records). Useful as a cheap pre-flight: `walker search foo
--count-only` returns just `{"type": "summary", "hits": N, ...}`
without paying for snippet extraction or context-turn assembly. The
walker still scans every surviving file to count, but it skips the
per-hit snippet/context work, so the overhead vs. a full search is
small and the *output* size is bounded regardless of match count —
exactly what protects an agent that stupidly asks a 1000-hit query.

### Errors

Per existing SPEC.md: exit 0 with a single JSON output on success,
non-zero with stderr diagnostic on bad input. The search command MUST
NOT panic on a malformed JSONL line — skip it silently like the cost
walk does.

Specific error shapes:

- Empty `<pattern>`: exit 2, stderr `pattern must be non-empty`.
- `--regex` with unparseable pattern: exit 2, stderr `bad regex: <why>`.
- `--since`/`--until` unparseable: exit 2, stderr `bad time: <flag>=<value>`.
- Both `--cwd` and `--any-cwd` set: exit 2, stderr (mutually exclusive).

## Overflow

If the unfiltered hit count would exceed `--limit`:

- Emit the first `limit` hits in chronological order (newest first).
- Set `truncated: true` in the summary.
- Emit a stderr diagnostic suggesting `--since` narrowing.

No streaming pagination cursor in v1 — agents that hit the cap should
re-query with a tighter time window. Cursor-based pagination is a v2
concern.

## Performance budget

Goal: ≤500ms for a single-host substring search over 14d of
transcripts on the bench corpus. The cost walk hits ~88ms (C++) /
~141ms (Go) for the same file set; search will be slower because it
reads the full text bodies instead of just `usage` fields, but the
mtime prune still applies and the regex/substring check is cheap
relative to JSON parse.

Cross-machine via SMB mount: ≤5s, same caveats as the cost walk's
multi-root mode (the network mount dominates). Same graceful-degradation
rule: if a configured root is unreachable, log to stderr and continue
with reachable roots — never block indefinitely.

## Conformance fixtures

`shared/corpus/search/<scenario>/<sid>.jsonl` plus sibling
`expected.json` mapping flag combinations → expected hit list. At
minimum:

1. **basic** — three sessions with one match each, default flags.
2. **multi-match-per-session** — one session with multiple matches;
   verify all are emitted and ordered correctly.
3. **bare-string-user-content** — older-format user message with
   string content (not array); verify it matches and isn't dropped.
4. **role-filter** — same pattern in both user and assistant turns;
   verify `--role user` and `--role assistant` partition correctly.
5. **tool-block-skip** — pattern only appears inside a `tool_result`;
   default (skip tool blocks) → 0 hits; `--include-tool-blocks` → 1 hit.
6. **regex** — `--regex 'foo\d+'` against text with `foo1`, `foo`,
   `foo42`; verify exactly 2 matches.
7. **case** — default case-insensitive returns 3 hits;
   `--case-sensitive` returns 1.
8. **time-window** — three matches across 30 days; `--since 7d`
   returns only the newest.
9. **count-only** — pattern matching 5 messages; default returns 5
   hits + summary; `--count-only` returns only the summary record
   with `hits: 5`.
10. **context-zero** — pattern with a hit in the middle of a 7-turn
    session; `--context 0` returns the hit message with empty
    `context_before` / `context_after` arrays.

Equality is structural over the JSON output, ignoring `elapsed_ms`
and `files_walked` (they vary across runs and impls).

## Decided constraints

These were open during spec review; settled here so implementers
don't re-litigate.

- **Regex flavor: RE2.** All four language impls constrain the public
  regex surface to RE2-compatible syntax (no lookaround, no
  backreferences). Rust's `regex` crate and Go's `regexp` enforce this
  natively; the C++ and Zig impls must reject patterns containing
  lookaround/backref syntactic forms at parse time so cross-impl
  conformance stays honest.
- **Multi-line.** Search treats newlines as whitespace for substring
  matches; regex respects explicit `(?m)` mode in the pattern itself.
  No dedicated `--multiline` flag in v1.
- **Snippet boundaries.** Per-char window with a word-boundary nudge —
  extend the cut point left/right to the nearest whitespace within ±20
  chars. Cheap, good enough; revisit only if hits look ugly in
  practice. The `--snippet-chars` flag gives the user the override
  when they want tighter or looser bounds; `--context 0` plus a small
  `--snippet-chars` gives maximally terse output for "I have a ton of
  targeted snippets," and a large `--context` plus the default
  `--snippet-chars` gives exploratory recall.

---

# MCP shim

## Why MCP, not (only) a skill

Three reasons MCP wins for *this* feature:

1. **Auto-discovery.** Skills require trigger phrases in the user's
   message; MCP tools show up in every session's tool list whether the
   conversation hints at them or not. The "agent didn't think to look"
   failure mode is exactly what MCP closes.
2. **In-conversation arguments.** "Find the session where I said X
   between March and April, only in skills-dev" is a structured query
   with five-ish arguments. MCP serializes that as a typed tool call
   instead of a freeform CLI string the agent has to construct.
3. **Cross-cwd by default.** MCP tools aren't bound to the current
   directory — they're registered per-host. Search is inherently
   cross-cwd. A CLI from cwd `~/foo` works fine, but the agent might
   not realize it can be invoked when working in `~/foo`. The MCP tool
   just is what it is, everywhere.

A skill can still ship alongside as the cheat-sheet for the *raw* CLI
when an agent prefers it (e.g., for batch operations the MCP tool
shouldn't handle). But the MCP path is the agent's default.

## Server shape

Match the projdash convention:

- **Framework.** `mcp.server.fastmcp.FastMCP` (the same `mcp>=1.0`
  Python SDK projdash uses).
- **Repo location.** `claude-walker/mcp/` Python package. The shim
  subprocesses the installed C++ winner at `~/.claude/walker.exe` (or
  `~/.local/bin/claude-walker` on Linux), discovering the binary via:
  1. `CLAUDE_WALKER_BINARY` env var if set.
  2. `~/.claude/walker.exe` / `~/.claude/walker`.
  3. `~/.local/bin/claude-walker.exe` / `~/.local/bin/claude-walker`.
  4. `PATH` lookup for `claude-walker`.
  First hit wins. On miss, every tool returns an MCP error suggesting
  `install.sh` / `install.bat`.
- **Logging.** Same JSONL request log pattern projdash uses
  (`~/.claude-walker-mcp.log`). Optional but cheap.
- **Registration.** Add to the user's `~/.claude.json` (user-scope,
  not per-project) so it's available from every cwd, mirroring
  projdash's pattern.

## Tool surface (v1)

One tool. Resist the urge to split.

### `claude_walker_search`

**Description (verbatim for the MCP `description` field):**

> Search past Claude Code session transcripts across all configured
> roots (including cross-machine mounted roots) for a substring or
> regex pattern. Returns matching messages with file paths, timestamps,
> and surrounding context. Use this when the user says something like
> "you said X a few sessions ago" or asks to find a past conversation
> — sessions on the other machine are often where the agent forgets
> to look.

**Parameters (pydantic-style schema):**

| Name              | Type                       | Required | Default | Notes                                                       |
| ----------------- | -------------------------- | -------- | ------- | ----------------------------------------------------------- |
| `pattern`         | str                        | yes      | —       | The pattern to search for.                                  |
| `regex`           | bool                       | no       | false   |                                                             |
| `case_sensitive`  | bool                       | no       | false   |                                                             |
| `role`            | Literal["user","assistant","both"] | no | "both"|                                                             |
| `since`           | str (RFC3339 or relative)  | no       | none    | e.g. `"7d"` or `"2026-03-01"`.                              |
| `until`           | str                        | no       | none    |                                                             |
| `cwd_slug`        | str                        | no       | none    | Project slug to restrict to.                                |
| `context_turns`   | int                        | no       | 1       | Turns of context before AND after each hit.                 |
| `limit`           | int                        | no       | 50      |                                                             |
| `count_only`      | bool                       | no       | false   | Emit only the summary record (no hits). Cheap pre-flight to size a query.                                |
| `include_tool_blocks` | bool                   | no       | false   |                                                             |

**Return shape:** the deserialized JSONL output from
`walker search --format jsonl ...`, parsed into a structured response:

```json
{
  "hits": [ { ... hit objects ... } ],
  "summary": { ... summary object ... }
}
```

**Errors propagated to MCP layer:**

- Binary not found → MCP error with install hint.
- Non-zero exit from walker → MCP error with stderr passed through.
- Subprocess timeout (>30s) → MCP error; the walker should never take
  that long unless a network root is hung, and the CLI is supposed to
  handle that gracefully — if it doesn't, the timeout is the safety net.

## Skill (optional companion)

Only worth shipping if MCP discovery turns out insufficient in
practice. Pre-emptive design:

- **Trigger phrases:** "you said X a few sessions ago", "find the
  conversation where", "what did we decide about", "I told you about",
  "search past sessions", "look back through transcripts".
- **Body (~30 lines):** trigger list, one-paragraph explainer, MCP
  tool name + the killer reminder *"cross-machine sessions are the
  common miss — `host_root` in the response tells you which mount the
  hit came from."*, optional CLI fallback cheat sheet for batch use.

Defer building this until we observe 2+ sessions where the agent
should have reached for `claude_walker_search` and didn't.

## Verification

Before declaring this spec done:

- [ ] Cross-impl conformance: every language impl passes the search
      fixtures within structural-JSON equality.
- [ ] MCP shim smoke: launch the FastMCP server, list tools, call
      `claude_walker_search` with a known-good pattern, verify the
      response shape.
- [ ] Cross-machine smoke: with `~/.claude/walker-roots.json`
      configured for the other host's mount, verify a search returns
      hits with the remote `host_root` populated.
- [ ] Graceful degradation smoke: with the remote mount disconnected,
      verify the tool returns local-only hits + a stderr-style
      diagnostic in the summary, no hang.

## Out of scope (filed for follow-up)

- `list-sessions` subcommand (metadata-only queries, no content match).
- Semantic search via embeddings.
- Per-tool / per-cost rollups (separate subcommand if/when needed).
- Mutation tools (annotate, tag, delete sessions) — not building.
- Streaming results for very large match counts.
