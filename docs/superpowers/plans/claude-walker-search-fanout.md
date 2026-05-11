# Handoff — claude-walker search subcommand: cross-impl fanout

**Predecessor:** `~/skills-dev/docs/superpowers/plans/claude-walker-search.md`
(deliverables #1–#3 done). The spec at
`~/skills-dev/docs/superpowers/specs/claude-walker-search.md` is still the
source of truth for CLI shape, semantics, and decided constraints — read
that first if you're picking this up cold.

This handoff covers deliverables #4 (Go/C++/Zig ports), #5 (MCP shim),
and #6 (SPEC fold-back). It's the driver brief for the session that
takes the search subcommand from "rust-only reference" to "all four
impls pass + MCP tool live + spec merged."

## Branch state when you pick this up

- **Worktree:** `~/claude-walker-worktrees/search-subcommand` on branch
  `search-subcommand`, pushed to both `origin` (GitHub) and `gitea`
  (Gitea). For claude-walker the remote naming is the opposite of
  skills-dev submodules — `origin = github.com:mtschoen/claude-walker`,
  `gitea = gitea@llamabox.internal:schoen/claude-walker`.
- **Commits on the branch (oldest → newest):**

  | sha | scope | what |
  |---|---|---|
  | `94ddf22` | fixtures | `shared/generate_search_corpus.py` + 10 scenarios with sibling `expected.json` files. |
  | `e70d169` | harness | `shared/conformance.py` adds `run_walker_search`, `assert_search_combo`, `check_search`, gated on `IMPLS_WITH_SEARCH` (empty at this commit). |
  | `b866493` | rust impl | `rust/src/content.rs` (extracted helpers, replaces beacons.rs locals), `rust/src/search.rs` (~680 lines), main.rs wiring; flips `IMPLS_WITH_SEARCH = {"rust"}`. |
  | `fe46228` | plan | PLAN.md inbox entry for the cross-machine walker-roots port follow-up to non-cpp impls. |

- **Conformance state:** `python shared/conformance.py rust` from the
  worktree passes 17/17 search combos plus all existing cost / beacons-
  latest / beacons-history / multi_root checks.

## Preconditions to verify before fanning out

```bash
cd ~/claude-walker-worktrees/search-subcommand
git status                           # clean
git log --oneline origin/main..HEAD  # 4 commits, matching the table above
git log --oneline gitea/main..HEAD   # same 4 commits (after `git fetch gitea`)
python shared/conformance.py rust    # all search/* combos green
```

If anything is dirty or has drifted, **stop and ask** before adding to
the branch. The fanout is meant to ADD commits, not rewrite.

### Permission grants (required for parallel subagent dispatch)

Per the user's global CLAUDE.md, project-local allowlists don't propagate
into worktree subagents — the `.git` boundary stops the search.
Confirm before fanning out:

```bash
grep -E '"Bash\(\*\)"|"Edit\(\*\*\)"' ~/.claude/settings.json
```

Should print both lines. If not, ask the user to add them (or use the
"full send" idiom for standing approval) before dispatching the parallel
fleet. **Sequential single-language work from the foreground session is
fine without them** — only the Task-tool fan-out needs the global grants.

## Smoke test results from the previous session

A real-recall smoke test ran in the session that authored this handoff
(searching for the first conversation that decided to create
claude-walker). Tool performance against the live local fleet:

- 137 hits across 17 sessions, 672 files walked, **1132ms** with
  default flags.
- No panics on malformed transcript lines (real corpus includes
  thinking-block signature blobs, file-history-snapshot entries,
  attachment entries, etc.).
- `--cwd <slug>` correctly scoped to one project.
- `--until <RFC3339>` worked for bisecting backward from the truncated
  full set.
- Truncation hint (*"truncated to --limit=N (had M total); narrow with
  --since"*) nudged toward the right next move.

The answer was found end-to-end via the search subcommand, then needed
one manual grep through the raw JSONL to retrieve the *exact* user
message — which surfaced the gap covered in the next section.

If you re-smoke after revising for queue-operation entries, repeat the
above plus the regex / count-only / empty-pattern / bad-regex /
bad-time error-path probes to confirm no regressions.

## Pre-fanout: queue-operation entries (gates fanout)

**The finding.** The smoke test found the agent's *acknowledgement* of
the redirect (a regular assistant text message) but missed the user's
*actual pivot prompt* because the user typed it during a tool call and
it landed as a `type: "queue-operation"` entry in the transcript, not
as a `type: "user"` message with text content. The current spec
(content-extraction section) only reaches messages with `role: user`
or `role: assistant`. Queue-op entries are invisible.

This is meaningful: the killer recall use case is "find the time I
told the agent X." Anything you typed while the agent was busy lives
in queue-op entries. **That's exactly the pile this tool should
surface.**

**Concrete data shape** observed in the smoke test session:

```json
{"type":"queue-operation","operation":"enqueue","timestamp":"...",
 "sessionId":"...","content":"would be cool to try doing this..."}
{"type":"queue-operation","operation":"popAll","timestamp":"...",
 "sessionId":"...","content":"would be cool to try doing this..."}
{"type":"queue-operation","operation":"enqueue","timestamp":"...",
 "sessionId":"...","content":"would be cool to try doing this... since it's broadly useful"}
{"type":"queue-operation","operation":"remove","timestamp":"...",
 "sessionId":"..."}
```

Note `content` lives at the entry root, not under `message.content`.
The `enqueue` operations stream as the user types (multiple, with
growing partial content); `popAll` is what the agent actually saw; the
final `enqueue` before processing carries the completed prompt.

**Work to do** before fanning out the Go/C++/Zig ports — keep this
on the `search-subcommand` branch:

1. **Spec revision** in `~/skills-dev/docs/superpowers/specs/claude-walker-search.md`:
   - Extend the "Content extraction" section to cover queue-op
     entries. `entry.content` (string at root) replaces `extract_text`
     when the entry's `type` is `queue-operation`.
   - **Open design question — decide before implementing:** dedupe
     strategy across the enqueue/popAll/remove sequence. Recommended:
     emit one hit per `popAll` (the agent-processed snapshot) plus
     the last `enqueue` before each `popAll` if its content differs
     materially. Alternative: emit every `enqueue` (noisy but
     complete). Either pick is encodable as a fixture scenario.
   - Decide the hit's `role` field for queue-op entries. Recommended:
     `"user"` (it's user input, just queued — keeps `--role user`
     working as you'd expect).
   - Update the filters section: queue-ops are user input, so role
     filtering treats them as `user`; tool-block-skip doesn't apply
     (no tool blocks involved). Add a quick note about the
     enqueue/popAll dedup semantics.
2. **Fixture scenario** `11-queue-operation/` in
   `shared/corpus/search/`:
   - sid1.jsonl with the enqueue→enqueue→popAll→remove sequence
     observed in the real corpus (the smoke test session
     `9cf1e57a-…` line range 217-223 is a clean template — see
     `~/.claude/projects/C--Users-mtsch-schoen-claude-status/9cf1e57a-57f3-4775-8cf3-2c4597b517ba.jsonl`
     for the exact shape).
   - At least two flag combos: `default` (the dedup picked above) and
     `role-assistant` (proves queue-ops don't leak into the assistant
     side).
3. **Rust impl** in `rust/src/search.rs` and `rust/src/content.rs`:
   - `scan_file` recognizes `type: "queue-operation"` entries and
     emits a `ScanMessage` with role=`"user"`, text=`entry.content`,
     and the dedup decided in step (1).
   - Decision: extend `extract_text` to take an optional entry-type
     parameter, OR add a new `extract_queue_op_text` helper in
     `content.rs`. The latter is cleaner because the data shape is
     genuinely different (content is at the root, not under
     `message.content`).
4. **Conformance and smoke**:
   - `python shared/conformance.py rust` passes the new 11-* scenario
     plus all existing.
   - Re-run the recall smoke from the previous session — the query
     `walker search "would be cool to try doing this in all 4
     languages"` should now find the user's pivot prompt directly,
     not just the agent's acknowledgement.
5. **Commit shape** on `search-subcommand`:
   - `search: queue-operation entries in content extraction` —
     bundle spec, fixtures, rust impl, content.rs helper.
   - Push to both `origin` (GitHub) and `gitea`.
6. **Update this handoff** — note the revision is done, drop this
   whole section, and remove the queue-op gotcha from the Go/C++/Zig
   per-language notes so the fanout subagents inherit the corrected
   spec verbatim.

Only after this lands should the Go/C++/Zig fanout begin — otherwise
the ports inherit a known gap and have to be re-revised in lockstep
later, which is more work than fixing it once on the reference.

**Cross-impl implication for fanout subagents** (after step 1 lands):
each port must also recognize queue-op entries. Add an explicit line
to their briefings: "queue-operation entries with `type: queue-
operation` are user input — index per the spec's dedup rule, same as
the rust impl."

## Deliverable #4: Go / C++ / Zig ports

The plan's commit convention: one commit per impl with scope prefix:
`search: go impl`, `search: cpp impl`, `search: zig impl`.

### Recommended dispatch order

Per the parent plan: **Go first** (sonic JSON parser, idiomatic enough
to expose spec ambiguity), **C++ second** (simdjson, the perf winner
and the production binary the MCP shim subprocesses), **Zig last**
(smallest impl; spec is most-stable by then).

### Common briefing for every subagent

Each port subagent gets the same five things in its prompt:

1. **Spec path:** `~/skills-dev/docs/superpowers/specs/claude-walker-search.md`
   — source of truth for flags, semantics, output shape.
2. **Rust reference:** `~/claude-walker-worktrees/search-subcommand/rust/src/search.rs`
   and `rust/src/content.rs`. Read both before writing a line.
3. **Worktree:** `~/claude-walker-worktrees/search-subcommand`. They commit
   onto the same `search-subcommand` branch. Build into the language's
   existing output path (so the conformance harness's `CANDIDATES` finds
   the binary without changes).
4. **Conformance bar:** from the worktree,
   `python shared/conformance.py <lang>` must pass all 17 search combos
   across 10 scenarios AND all pre-existing cost / beacons checks.
   They must add `"<lang>"` to `IMPLS_WITH_SEARCH` in `shared/conformance.py`
   as the last line of their commit.
5. **Hard constraints:**
   - Do NOT modify other impls' code.
   - Do NOT touch the spec.
   - Do NOT touch the existing fixtures or generate_search_corpus.py.
   - Do NOT touch the conformance.py harness except for the
     IMPLS_WITH_SEARCH allow-list line.
   - If they find a spec ambiguity, STOP and surface it — don't
     unilaterally pick a behavior.

### Per-language notes

These are the things each port is likely to wrestle with. The rust
impl is the answer key for most.

#### Go

- **Match the existing `go/` style.** Uses `bytedance/sonic` for JSON.
  For search, prefer parsing each transcript line into `*sonic.Node`
  (untyped) so the bare-string-vs-array content branch is uniform —
  same reason the rust impl uses `serde_json::Value` instead of a
  typed `Content` enum.
- **Regex:** `regexp` package is RE2 by design — no extra validation
  needed for lookaround/backref rejection. `(?i)` prefix for case
  insensitivity is supported.
- **Time parsing:** RFC3339 via `time.Parse(time.RFC3339, s)`. Relative
  form (Nd/Nh/Nm/Ns) is a small custom parser.
- **Discovery:** `filepath.Glob("<root>/<slug>/*.jsonl")`. Mtime via
  `os.Stat`.
- **Output:** `encoding/json` for the JSONL records (sonic is overkill
  for a few records per call; consistency with cost-mode's choice is
  fine either way). Pretty mode mirrors rust.
- **Concurrency:** rust uses a sequential file loop (rayon was deemed
  overkill for the corpus sizes search will see). Go can match that —
  goroutine-per-file is a bench follow-up, not v1.

#### C++

- **Match the existing `cpp/` style.** Uses `nlohmann/json` + simdjson
  on demand. For search, simdjson ondemand is the natural fit, but the
  loose-Value pattern is more complex in simdjson than serde_json — the
  port may find it cleaner to use `nlohmann::json` for the per-message
  parse and accept the perf hit (search isn't the hot path; cost-mode
  is).
- **Regex:** `<regex>` is ECMAScript-flavored (NOT RE2) and slow. Two
  options:
  1. **Use `<regex>` + a syntactic pre-validator** that rejects
     patterns containing lookaround `(?=...)`, `(?!...)`, `(?<=...)`,
     `(?<!...)` or backreferences `\1..\9` at parse time. Crude regex
     over the pattern string works.
  2. **Link Google's RE2 library** (`re2/re2.h`). Cleaner; adds a
     dependency to CMakeLists.txt.

   For symmetry with rust/go/zig the spec explicitly requires RE2
   surface compatibility — option (1) is the lighter-weight route.
- **Time parsing:** `<chrono>` parse_rfc3339 (C++20) or a small manual
  parser. Relative form: split on trailing unit char.
- **Discovery:** `std::filesystem::recursive_directory_iterator` with
  the slug-glob pattern. Mtime via `fs::last_write_time`.
- **Walker-roots is already there.** cpp ALREADY supports
  `--extra-projects-root` and `--no-config` via `walker_roots.hpp`.
  Search should plug into the same `resolve_roots()` call so multi-root
  cross-machine search works on cpp from day one. Set `host_root` per
  hit to the root that yielded it, not just the first.
- **`--no-config` from the conformance harness:** Already wired via
  `IMPLS_WITH_NO_CONFIG = {"cpp"}`. The port doesn't need to do anything
  special; just keep the flag working.

#### Zig

- **Match the existing `zig/` style.** Uses manual `std.json` parsing —
  field scanning rather than full deserialization. The same approach
  works for search: scan each line for `message.role`, `message.content`,
  and `timestamp`, branching on whether content is a string or an array.
- **Regex:** Zig std has no regex. Options:
  1. **Bring in a third-party regex library** (e.g.
     [tiehuis/zig-regex](https://github.com/tiehuis/zig-regex), if it's
     RE2-compatible; verify before depending on it).
  2. **Substring-only impl for v1**, with `--regex` returning exit 2 and
     a stderr "regex not supported in zig v1; use rust/go/cpp for regex
     queries". This DROPS scenario 06 from the conformance bar for zig
     specifically — add `"zig"` to a new `IMPLS_WITHOUT_REGEX` set and
     have `check_search` skip the regex scenario for those impls.

   The spec's wording ("All four language impls constrain the public
   regex surface to RE2-compatible syntax") implies four supported
   impls, so option (1) is the spec-honoring choice if a good library
   exists. **Stop and ask the user** before picking (2) — it's a real
   capability gap.
- **Time / discovery / output:** standard `std.time`, `std.fs.walk`,
  `std.json.stringify`.

### Cross-cutting gotchas

- **Newline-normalize for substring.** Spec: "Search treats newlines as
  whitespace for substring matches." The rust impl gets this for free
  because substring matching is just `regex::escape(pattern)` against
  the raw text — newlines inside the text don't break the match (they
  just aren't IN the pattern). Other impls following the same pattern
  inherit the same behavior. Don't manually strip newlines.
- **Word-boundary snippet nudge.** ±20 chars from the cut point, look
  outward (toward 0 from left cut, toward len from right cut). The rust
  helpers `nudge_to_whitespace` and `nudge_char_boundary` are the answer
  key — port them faithfully.
- **Match offsets are snippet-relative**, not full-text-relative. After
  building the snippet, re-find matches inside the snippet substring.
  The rust impl does this with `find_all_matches(re, &snippet)` after
  the snippet is sliced.
- **Context is positional and unfiltered.** Hit's `context_before` /
  `context_after` show actual transcript neighbors regardless of which
  filter excluded their hit-candidacy. This is the decided behavior
  encoded in fixture 04 (role-filter shows context crossing the role
  boundary) and fixture 08 (time-window shows the 3d-old hit's
  context_before containing the 14d-old message even with `--since 7d`).
- **Newest-first ordering with stable tiebreak.** Rust sorts by
  `(timestamp DESC, session_id ASC, line_number ASC)` for determinism
  when multiple messages share a timestamp (rare in practice; common in
  fixtures where I used round-second timestamps for some scenarios).
  Match that tiebreak or fixtures may pass on rust but fail elsewhere.
- **`sessions_matched` is pre-truncation.** Count distinct sessions
  that produced ≥1 match before applying `--limit`. None of the v1
  fixtures hit `--limit` so this is unobservable in conformance, but
  the field semantic is decided.
- **`roots_walked = 1` in v1 for single-root impls.** Always 1 when
  `--projects-root` is given (or default), regardless of whether the
  root yielded files. cpp grows this to `len(resolved_roots)` since it
  has walker-roots support.

## Deliverable #5: MCP shim

Gated on **at least cpp** passing conformance (since cpp is what
`install.bat` deploys to `~/.claude/walker.exe`, which the shim
subprocesses). Worth doing in parallel with the final port (zig) if you
want to compress wall-clock — they don't share files.

- Repo location: `claude-walker/mcp/` Python package.
- `pyproject.toml` declares `mcp>=1.0`.
- `mcp/__main__.py` launches the FastMCP server.
- `mcp/server.py` exposes `claude_walker_search` (one tool — resist
  splitting). Discovery chain:
  1. `$CLAUDE_WALKER_BINARY` env var.
  2. `~/.claude/walker.exe` / `~/.claude/walker`.
  3. `~/.local/bin/claude-walker.exe` / `~/.local/bin/claude-walker`.
  4. `PATH` lookup for `claude-walker`.
- Log to `~/.claude-walker-mcp.log` (JSONL `call`/`return`/`error`)
  mirroring projdash's pattern. Useful for hang diagnosis later; cheap
  to add now.
- Subprocess timeout 30s.
- Reference shape: `~/projdash/src/projdash/mcp/server.py`.

Smoke test before going live:

```bash
# From the worktree:
python -m mcp_dev_tool list-tools claude_walker.mcp.server
# or run the projdash test pattern equivalent.
```

Register in `~/.claude.json` (user-scope, not project-scope) when ready.

## Deliverable #6: SPEC fold-back

Once all four impls pass conformance AND the MCP shim works:

1. **Add a "Search" subsection to `claude-walker/SPEC.md` `## Subcommands`**
   (after `beacons-history`). Pull the CLI shape + match semantics +
   filters + output + decided constraints from the spec file. Drop
   anything pre-implementation ("DRAFT", implementation hygiene note,
   etc.).
2. **MCP shim shape graduates** to either:
   - A new `claude-walker/SPEC-mcp.md` if it'll grow beyond search, or
   - Stay in skills-dev/docs/superpowers/specs/ if search is the only
     MCP-exposed tool for the foreseeable future.

   Either is fine — your call based on the state of the world at that
   point.
3. **Delete the scaffolding:**
   - `~/skills-dev/docs/superpowers/specs/claude-walker-search.md`
   - `~/skills-dev/docs/superpowers/plans/claude-walker-search.md`
   - `~/skills-dev/docs/superpowers/plans/claude-walker-search-fanout.md`
     (this file).

4. **Final commit on the branch:** `search: SPEC fold-back; remove
   scaffolding` (in claude-walker), and a paired commit in skills-dev
   that bumps the submodule pointer + removes the docs files.

## Verification bar before merging

From the parent spec's `## Verification` section:

- [ ] Cross-impl conformance: rust ✓ (done), go, cpp, zig all pass the
      10 fixtures.
- [ ] MCP smoke: launch FastMCP, list tools, call `claude_walker_search`
      with a known pattern, verify response shape.
- [ ] Cross-machine smoke: with `~/.claude/walker-roots.json` configured
      for the other host's mount (`/mnt/llamabox/...` or
      `Y:\.claude\projects`), verify a search returns hits with the
      remote `host_root` populated. **Targets cpp specifically** since
      that's the only impl with walker-roots support on this branch.
- [ ] Graceful degradation smoke: disconnect the remote mount, verify
      the tool returns local-only hits + stderr diagnostic, no hang.

All four must pass before the SPEC fold-back commit.

## Out-of-scope reminders

Reiterating the parent spec's non-goals so a port subagent doesn't
expand scope on its own:

- **No semantic / embedding search.** Substring + regex only.
- **No on-disk index.** Linear scan is fine.
- **No mutation tools.** Read-only.
- **No `--root` alias.** `--projects-root` only.
- **No `--multiline` flag.** Regex `(?m)` covers it.
- **Regex is RE2.** Reject lookaround / backref at parse time (cpp+zig
  need this validator; rust/go get it for free from their regex
  libraries).

If a port reveals a real reason to relax any of these, STOP and ask.
Don't widen scope unilaterally.

## File index

- **Parent spec (still authoritative):**
  `~/skills-dev/docs/superpowers/specs/claude-walker-search.md`
- **Parent plan (delivers 1–3 done, 4–6 deferred to this handoff):**
  `~/skills-dev/docs/superpowers/plans/claude-walker-search.md`
- **This handoff:** `~/skills-dev/docs/superpowers/plans/claude-walker-search-fanout.md`
- **Branch state:** `~/claude-walker-worktrees/search-subcommand` on
  `search-subcommand`, pushed to `origin` (GitHub) and `gitea` (Gitea).
- **Reference impl:**
  - `rust/src/search.rs` (search logic)
  - `rust/src/content.rs` (shared content extraction)
  - `rust/src/beacons.rs` and `rust/src/main.rs` (wiring example)
- **Conformance harness:** `shared/conformance.py` (extend
  `IMPLS_WITH_SEARCH` per port; do NOT add new scenarios without
  updating the spec first).
- **cpp walker-roots reference:** `cpp/walker_roots.hpp` (for the cpp
  port's multi-root integration).
- **MCP reference:** `~/projdash/src/projdash/mcp/server.py`.

## First message to send the next session

> Picking up the search-subcommand fanout. Verified preconditions
> (worktree clean, 4 commits on `search-subcommand` matching the
> handoff log, rust conformance green, global Bash(*)/Edit(**) grants
> in place if fanning out subagents). Starting with the pre-fanout
> queue-operation revision (gates everything else); will commit on
> the same branch and report before starting the Go/C++/Zig fanout.
