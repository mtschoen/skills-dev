# Implementation plan — claude-walker session search

**Spec:** `~/skills-dev/docs/superpowers/specs/claude-walker-search.md`
(read this first; it's the source of truth for the CLI shape, semantics,
and decided constraints).

This plan is the **driver brief** for the new session implementing
that spec. Read top-to-bottom before starting.

## Preconditions to verify before the first edit

The user reports the parallel session has wrapped, but verify anyway —
sessions can be marked "done" while leaving stale state:

```bash
cd ~/claude-walker
git status                           # expect clean
git log --oneline origin/main..main  # expect empty (everything pushed)
git log --oneline origin/main -5     # see what landed
```

If status is dirty or unpushed commits exist, **stop and ask the user**
before doing anything else.

Also confirm the idle-exclusion port status in `~/claude-walker/PLAN.md`'s
Inbox section — if all four impls (Rust/Go/C++/Zig) have the new
`active_elapsed` field, great. If only some do, do NOT block on this;
the search subcommand is orthogonal to beacons-history and doesn't need
all four impls in sync to start.

### Permission check (this matters; silent failures otherwise)

Per the user's global CLAUDE.md, subagent permissions don't propagate
into worktrees — project-local allowlists stop at the `.git` boundary.
Before dispatching any parallel subagents from inside the worktree
(which is the natural shape for the Go/C++/Zig ports later), verify
`~/.claude/settings.json` (global) contains broad grants:

```bash
grep -E '"Bash\(\*\)"|"Edit\(\*\*\)"' ~/.claude/settings.json
```

If those aren't there and you plan to fan out subagents, ask the user
to add them up front. Sequential single-language work from the
foreground session is fine without them — only the fan-out needs the
global grants.

## Worktree setup

A worktree off claude-walker, on a fresh branch:

```bash
cd ~/claude-walker
git worktree add ~/claude-walker-worktrees/search-subcommand -b search-subcommand main
cd ~/claude-walker-worktrees/search-subcommand
```

If `~/claude-walker-worktrees/` doesn't exist yet, `git worktree add`
creates it. Use `superpowers:using-git-worktrees` skill if you want the
canonical setup ceremony — it handles edge cases like an already-existing
branch name.

## Deliverable sequence (stop and review between each numbered item)

The plan is sequential with explicit stop points. Do **not** chain
through more than one item without coming back to the user.

### 1. Conformance fixtures first

Before any Rust code. Create the corpus per spec §"Conformance fixtures":

```text
shared/corpus/search/
  01-basic/{sid1.jsonl, sid2.jsonl, sid3.jsonl, expected.json}
  02-multi-match-per-session/{sid1.jsonl, expected.json}
  03-bare-string-user-content/{sid1.jsonl, expected.json}
  04-role-filter/{sid1.jsonl, expected.json}
  05-tool-block-skip/{sid1.jsonl, expected.json}
  06-regex/{sid1.jsonl, expected.json}
  07-case/{sid1.jsonl, expected.json}
  08-time-window/{sid1.jsonl, expected.json}
  09-count-only/{sid1.jsonl, expected.json}
  10-context-zero/{sid1.jsonl, expected.json}
```

Each `expected.json` maps `{flag_combo_string → expected_hit_list}`.
Format choice: follow the precedent in `shared/corpus/beacons/<scenario>/`
(`expected_latest.json`, `expected_history.json`) — one file per
subcommand variant rather than one big mapping file.

Stop. Show the fixture set. Get sign-off before extending the harness.

### 2. Extend `shared/conformance.py` for the search subcommand

Add a `run_search_conformance(binary)` function that:

- Iterates `shared/corpus/search/*/`.
- For each fixture, runs `<binary> search <pattern> <flags> --format jsonl`
  with each flag combo from `expected.json`.
- Parses JSONL stdout, deserializes each line to a dict.
- Structural-compares against the expected list, ignoring `elapsed_ms`
  and `files_walked` (they vary per run).
- Reports pass/fail with diff snippets on mismatch.

The cost-mode conformance pattern is the template. Don't reinvent —
mirror its structure for the search dispatcher.

Stop. Show the harness changes. Confirm the test rig is sound before
writing the Rust impl that will be tested against it.

### 3. Rust impl as the reference

Touchpoints:

- `rust/src/main.rs` — extend the subcommand dispatch to recognize
  `search`. Existing pattern: see how `beacons-latest` and
  `beacons-history` are wired (cost defaults; named subcommands
  override).
- `rust/src/search.rs` — new module. Public entry point:
  `pub fn run(args: SearchArgs) -> Result<()>` writes JSONL or pretty to
  stdout.
- **Reuse the loose-`Value` content extraction** from
  `rust/src/beacons.rs` (`extract_text`, `user_content_is_tool_result`).
  The spec explicitly references these; do not write a new strict-typed
  parser — it'll drop ~10% of older user prompts. Move them to a shared
  module if not already there.
- Walk reuse: the existing rayon-based file walker in cost mode covers
  the multi-root, mtime-pruned, deduped pattern. Factor out if needed
  so search and cost share the discovery phase.

Implementation order inside Rust:

1. Flag parsing (clap derive or equivalent — match existing impl).
2. Multi-root discovery + mtime filter (factor out from cost if not
   already shared).
3. Per-file scanning loop with role / tool-block / time filters.
4. Pattern match (substring or regex per flag) — use `regex` crate;
   crate's syntax is already RE2-compatible.
5. Hit assembly: pull snippet with ±`snippet_chars/2` window and
   word-boundary nudge, collect context turns.
6. JSONL writer and pretty writer.
7. `--count-only` short-circuit: skip steps 5–6, just count + emit
   summary record.

Pass `python shared/conformance.py` from the worktree (it should run
all subcommands' fixtures including the new search ones).

Stop. Diff review. PR-shaped commit on the `search-subcommand` branch
in the worktree; push to `origin` (Gitea) for review before fanning
out to other impls.

### 4. (Optional, after review) Go/C++/Zig ports

Once Rust passes conformance and the user has reviewed the shape, the
remaining impls are **parallelizable** — each can be a subagent
dispatched from the worktree, with the Rust impl as the reference and
the conformance harness as the bar.

Suggested dispatch order: Go first (sonic JSON parser, idiomatic enough
to expose any spec ambiguity), then C++ (simdjson, the perf winner),
then Zig (smallest impl, last so the spec is most stable).

Each subagent gets:

- The spec path.
- The Rust impl as `rust/src/search.rs` reference.
- The conformance command they must pass.
- "Do not modify other impls; do not touch the spec."

The user's permission grants (preflight item above) must already be in
place if you fan these out from within the worktree.

### 5. MCP shim

After at least one impl passes conformance — preferably the C++ winner,
since that's what `install.bat` deploys to `~/.claude/walker.exe`.

Create `claude-walker/mcp/` Python package:

- `pyproject.toml` — depends on `mcp>=1.0`.
- `mcp/__main__.py` — entry point that launches the FastMCP server.
- `mcp/server.py` — `claude_walker_search` tool, subprocesses the
  binary discovered via the spec's discovery chain (`$CLAUDE_WALKER_BINARY`,
  `~/.claude/walker.exe`, `~/.local/bin/claude-walker`, then `$PATH`).
- Mirror projdash's logging pattern at `~/.claude-walker-mcp.log` —
  same JSONL `call`/`return`/`error` events for hang diagnosis.

Smoke test:

```bash
python -m mcp_dev_tool list-tools claude-walker.mcp.server
# OR launch FastMCP and call the tool directly; the projdash test
# patterns in ~/projdash/tests/ may have a runnable template.
```

Register in `~/.claude.json` (user-scope) when ready to go live.

### 6. SPEC.md merge

Once all impls pass and the MCP shim works, fold the CLI section of
the search spec into `claude-walker/SPEC.md`'s `## Subcommands` (after
`beacons-history`). MCP shim shape graduates to either a new
`claude-walker/SPEC-mcp.md` or stays in skills-dev — your call based
on whether it grows beyond search.

Delete `~/skills-dev/docs/superpowers/specs/claude-walker-search.md`
and this plan file after the merge.

## Verification bar before declaring done

From spec §"Verification":

- [ ] Cross-impl conformance: every language impl passes the search
      fixtures (10 scenarios).
- [ ] MCP smoke: launch FastMCP, list tools, call `claude_walker_search`
      with a known-good pattern, verify response shape.
- [ ] Cross-machine smoke: with `~/.claude/walker-roots.json` configured
      for the other host's mount (`/mnt/llamabox/...` or
      `Y:\.claude\projects`), verify a search returns hits with the
      remote `host_root` populated.
- [ ] Graceful degradation smoke: disconnect the remote mount, verify
      the tool returns local-only hits + stderr diagnostic, no hang.

All four must pass before merging the SPEC fold-back.

## Out-of-scope reminders

The spec lists these explicitly; the implementing session must NOT
expand scope without asking:

- **No semantic / embedding search.** Substring + regex only.
- **No on-disk index.** Linear scan is fine for v1.
- **No mutation tools.** Read-only across the board.
- **No `--root` alias.** Use `--projects-root` only; the future
  `--roots` plural rename is its own follow-up, not bundled here.
- **No `--multiline` flag.** Regex `(?m)` mode covers it.
- **Regex is RE2 only.** Reject lookaround/backref at parse time.

If the implementation reveals a real reason to relax any of these,
stop and ask — don't unilaterally widen scope.

## Commit conventions

- Branch: `search-subcommand` (set by the worktree command above).
- Per-impl commits with clear scope: `search: rust impl`,
  `search: conformance fixtures`, `search: go impl`, etc.
- Author: existing `Matt Schoen` git config — this is not a new repo,
  so the `claude-code` author override from skills-dev's CLAUDE.md
  doesn't apply.
- Push to `origin` (Gitea) only until ready for cross-mirror; the
  umbrella push via `~/skills-dev/scripts/push-all.{sh,bat}` handles
  the GitHub mirror once submodule pointers land in skills-dev.

## File index

- Spec: `~/skills-dev/docs/superpowers/specs/claude-walker-search.md`
- This plan: `~/skills-dev/docs/superpowers/plans/claude-walker-search.md`
- Existing CLI contract: `~/claude-walker/SPEC.md`
- Existing PLAN with current work context: `~/claude-walker/PLAN.md`
- Rust reference for content extraction: `~/claude-walker/rust/src/beacons.rs`
- Conformance harness: `~/claude-walker/shared/conformance.py`
- MCP server reference (FastMCP idioms): `~/projdash/src/projdash/mcp/server.py`

## First message to send the user

Open the implementing session with:

> Picking up the search-subcommand work. Verified preconditions
> (`git status` clean, no unpushed commits on main, idle-exclusion port
> state checked, global Bash(*)/Edit(**) grants confirmed if fanning
> out subagents). Worktree at `~/claude-walker-worktrees/search-subcommand`.
> Starting with deliverable #1: conformance fixtures. Will return for
> review before extending the harness.
