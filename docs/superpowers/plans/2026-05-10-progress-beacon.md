# Progress Beacon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the user a visible "when can I close my laptop" answer. The agent emits structured progress beacons (`<progress-beacon>` JSON blocks) periodically during non-trivial turns; claude-walker extracts them; schoen-claude-status renders raw + historically-calibrated ETA in the status line. Material drift surfaces as a loud in-line note (no blocking question), with ESC + verbal request as the user's override path.

**Architecture:** Three coordinated repos. `skills-progress-beacon/` (new) ships SKILL body + PostToolUse recency-nudge hook + evals. `~/claude-walker/` grows two new subcommands (`beacons-latest`, `beacons-history`) across all four language impls (Rust → C++ → Go → Zig), with C++ as the production binary. `~/schoen-claude-status/` patches `statusline.py`, `statusline_lib.py`, and `subagent_statusline.py` to render the live beacon and the calibrated ETA (computed from a 7-day median of `actual_elapsed / begin_eta` ratios, gated on `n_pairs >= 20`).

**Tech Stack:** Rust + C++ + Go + Zig (claude-walker conformance fleet); Python 3.x with `orjson` (statusline rendering); Bash (recency-nudge hook); Markdown (SKILL.md, README, observation log). No new external libraries beyond what claude-walker / schoen-claude-status already use.

---

## Working assumptions

- Working directory: `C:\Users\mtsch\skills-dev\` (umbrella). Other repos accessed by absolute path.
- Submodule workflow follows skills-dev's CLAUDE.md (Gitea primary, GitHub mirror, relative-URL `.gitmodules`).
- Default branch is `main` everywhere.
- User is on Windows (chonkers). Bash hook script must work via Git Bash on Windows; PowerShell-only constructs are out.
- `~/.claude/settings.json` already wires `statusLine` and `subagentStatusLine` to `~/schoen-claude-status/statusline-command.sh` and `…/subagent-statusline.sh`. No `settings.json` changes needed for status line.
- Hook config additions go in `~/.claude/settings.json` under `hooks.PostToolUse`.

---

## Phase 1: claude-walker beacon mode — Rust reference impl

Goal of this phase: a working `claude-walker beacons-latest` and `claude-walker beacons-history` in Rust, with conformance fixtures that any future language port must pass.

### Task 1.1: Author conformance fixtures + expected outputs

**Files:**
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/clean_lifecycle.jsonl`
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/malformed.jsonl`
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/missing_fields.jsonl`
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/multiple_in_turn.jsonl`
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/cross_session_pairs/session_a.jsonl`
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/cross_session_pairs/session_b.jsonl`
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/expected_latest.json`
- Create: `C:/Users/mtsch/claude-walker/shared/corpus/beacons/expected_history.json`

- [ ] **Step 1: Author `clean_lifecycle.jsonl`**

A minimal synthetic transcript with three assistant messages: a `begin` beacon, a `report`, and an `end`. Each line is one full Claude Code transcript entry (mimicking the real format — `type: "assistant"`, `message: {role: "assistant", content: [{type: "text", text: "..."}], id: "msg_..."}`, `timestamp: "ISO8601"`).

Example single line (the assistant's text content includes the fenced beacon block):

```json
{"type":"assistant","timestamp":"2026-05-10T12:00:00Z","message":{"id":"msg_001","role":"assistant","model":"claude-opus-4-7","content":[{"type":"text","text":"Starting work.\n\n<progress-beacon>\n{\"kind\": \"begin\", \"eta_seconds\": 180, \"summary\": \"running tests\", \"drift\": \"nominal\"}\n</progress-beacon>"}],"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}
```

The fixture should have three such lines: `begin` at `12:00:00Z`, `report` at `12:02:30Z`, `end` at `12:04:45Z`.

- [ ] **Step 2: Author `malformed.jsonl`**

A transcript with one assistant message whose beacon block contains broken JSON (e.g., trailing comma, unquoted key). Walker must silently skip — no beacon found.

- [ ] **Step 3: Author `missing_fields.jsonl`**

Beacon JSON parses but `drift` field is missing. Same — silently skipped.

- [ ] **Step 4: Author `multiple_in_turn.jsonl`**

Three assistant messages each containing a beacon (begin, report, report). Walker must return the LATEST (third) one.

- [ ] **Step 5: Author `cross_session_pairs/`**

Two session-shaped JSONLs. Each has a clean begin/end pair. Session A: begin says 600s, end emitted at +1020s actual. Session B: begin says 300s, end at +280s actual. Pairs ratios: 1.7 and ~0.93. Median ratio (`bias_factor`) = 1.32 (median of two values is the mean of the two when even count).

- [ ] **Step 6: Author `expected_latest.json`**

Document the expected `walker beacons-latest --session-id <X>` output for each fixture. Map of fixture path → expected JSON shape (excluding `elapsed_ms` which is impl-specific).

```json
{
  "clean_lifecycle.jsonl": {
    "beacon": {"kind": "end", "eta_seconds": 0, "summary": "...", "drift": "nominal"},
    "emitted_at": <iso-to-epoch>, "age_seconds": null
  },
  "malformed.jsonl": {"beacon": null},
  ...
}
```

- [ ] **Step 7: Author `expected_history.json`**

```json
{
  "pairs": [{"begin_eta": 600, "actual_elapsed": 1020}, {"begin_eta": 300, "actual_elapsed": 280}],
  "session_count": 2,
  "n_pairs": 2,
  "bias_factor": 1.32
}
```

- [ ] **Step 8: Commit**

```bash
cd C:/Users/mtsch/claude-walker
git add shared/corpus/beacons/ shared/corpus/beacons/expected_latest.json shared/corpus/beacons/expected_history.json
git commit -m "test: beacon-mode conformance fixtures"
```

### Task 1.2: Update SPEC.md with beacon subcommand contracts

**Files:**
- Modify: `C:/Users/mtsch/claude-walker/SPEC.md`

- [ ] **Step 1: Add subcommand section**

After the existing "CLI contract" section, add:

```markdown
## Subcommands

The bare `walker --period ... --win-start ...` invocation maps to
the `cost` subcommand. New subcommands extend the CLI:

### `beacons-latest --session-id <id> [--projects-root <path>]`

Walks the matching transcript (parent or `subagents/agent-<id>.jsonl`)
backwards, finds the most recent assistant message containing a
`<progress-beacon>...</progress-beacon>` block. JSON in the block
must parse and contain `kind`, `eta_seconds`, `summary`, `drift`
(plus optional `beats_left`).

Output: `{"beacon": {...} | null, "emitted_at": <epoch> | null,
"age_seconds": <num> | null, "elapsed_ms": <u64>}`.

If multiple beacons exist in the matching transcript, return the
one with the highest `timestamp`. Malformed JSON or missing
required fields → treat as no beacon (silently skip).

### `beacons-history --period <seconds> [--win-start <unix>] [--projects-root <path>]`

Walks the full fleet under the time window. For each session that
contains both a `kind: "begin"` AND a `kind: "end"` beacon within
the window, emits a `(begin_eta, actual_elapsed)` pair where
`actual_elapsed = end_timestamp - begin_timestamp`.

Computes `bias_factor = median(actual_elapsed / begin_eta)` across
all pairs.

Output: `{"pairs": [...], "session_count": <num>, "n_pairs": <num>,
"bias_factor": <f64>, "elapsed_ms": <u64>}`. If `n_pairs == 0`,
`bias_factor` is `null`.
```

- [ ] **Step 2: Commit**

```bash
git add SPEC.md
git commit -m "spec: beacons-latest + beacons-history subcommands"
```

### Task 1.3: Extend conformance harness to assert beacon outputs

**Files:**
- Modify: `C:/Users/mtsch/claude-walker/shared/conformance.py`

- [ ] **Step 1: Read current conformance.py to learn its assertion shape**

Run: `cat shared/conformance.py | head -80`
Note its current pattern (likely runs the binary, parses JSON output, compares to expected).

- [ ] **Step 2: Add beacon-fixture assertions**

After the existing cost-mode assertions, append a function `assert_beacons_latest(impl_path)` that for each fixture in `shared/corpus/beacons/*.jsonl`:
1. Invokes `<impl_path> beacons-latest --session-id <fixture-stem> --projects-root <fixture-dir>`.
2. Parses stdout JSON.
3. Strips `elapsed_ms` (timing-dependent).
4. Compares against `expected_latest.json[fixture-name]`.
5. Asserts equal, raises on mismatch.

Add `assert_beacons_history(impl_path)` similarly using `cross_session_pairs/` and `expected_history.json`. `bias_factor` comparison uses `±0.001` tolerance.

- [ ] **Step 3: Wire both into the harness's main()**

Existing main() iterates over impls and runs cost assertions. Add the two new beacon assertion functions to the same iteration.

- [ ] **Step 4: Run conformance harness — expect Rust to fail (impl not yet)**

```bash
python shared/conformance.py --impl rust
```
Expected: cost assertions pass (existing); beacon assertions fail (`beacons-latest` not implemented). This confirms the harness wiring is correct before we write impl code.

- [ ] **Step 5: Commit**

```bash
git add shared/conformance.py
git commit -m "test: conformance harness checks beacon subcommands"
```

### Task 1.4: Implement `beacons-latest` in Rust (TDD)

**Files:**
- Modify: `C:/Users/mtsch/claude-walker/rust/src/main.rs`
- Create: `C:/Users/mtsch/claude-walker/rust/src/beacons.rs`
- Modify: `C:/Users/mtsch/claude-walker/rust/Cargo.toml` (if `regex` not already a dep)

- [ ] **Step 1: Read main.rs to understand current arg parsing**

Run: `cat rust/src/main.rs | head -60`. Identify how it currently parses `--period`, `--win-start`. Likely a simple manual arg loop. We extend it: first positional arg is the subcommand (`cost`, `beacons-latest`, `beacons-history`); fall back to `cost` for back-compat is NOT needed (claude-walker is internal).

- [ ] **Step 2: Add `beacons` module declaration in main.rs**

Add `mod beacons;` near top. Add subcommand routing after arg parse:

```rust
let subcommand = std::env::args().nth(1).unwrap_or_else(|| "cost".to_string());
match subcommand.as_str() {
    "cost" => run_cost(/* existing args */),
    "beacons-latest" => beacons::run_latest(/* args */),
    "beacons-history" => beacons::run_history(/* args */),
    _ => { eprintln!("unknown subcommand: {}", subcommand); std::process::exit(2); }
}
```

- [ ] **Step 3: Stub `beacons.rs` with empty functions**

```rust
pub fn run_latest(_args: Vec<String>) {
    println!(r#"{{"beacon": null, "elapsed_ms": 0}}"#);
}

pub fn run_history(_args: Vec<String>) {
    println!(r#"{{"pairs": [], "session_count": 0, "n_pairs": 0, "bias_factor": null, "elapsed_ms": 0}}"#);
}
```

- [ ] **Step 4: Build + run conformance — confirm stubs return null/empty correctly for malformed/missing fixtures, fail for clean_lifecycle**

```bash
cd rust && cargo build --release
python ../shared/conformance.py --impl rust
```
Expected: malformed/missing fixtures pass (stub returns null which matches expected); clean_lifecycle fails (stub returns null, expected has a real beacon).

- [ ] **Step 5: Implement `beacons-latest` arg parsing in `beacons.rs`**

Parse `--session-id` and `--projects-root` from the args slice. Default `--projects-root` to `~/.claude/projects` (use `dirs::home_dir()` or `std::env::var("HOME")`).

Resolve transcript path: glob `<projects-root>/*/<session-id>.jsonl` first; if not found, glob `<projects-root>/*/*/subagents/agent-<session-id>.jsonl`. If neither matches, output `{"beacon": null, "elapsed_ms": <ms>}` and exit 0.

- [ ] **Step 6: Implement beacon extraction**

In `beacons.rs`, function `find_latest_beacon(jsonl_path: &Path) -> Option<(Beacon, f64)>`:

1. Open file, read lines (use `BufReader`).
2. For each line, attempt to parse as JSON. Skip on parse failure.
3. Filter to `entry.message.role == "assistant"`.
4. Extract `entry.message.content[*].text` (concatenate text-type content blocks).
5. Use `regex` crate to find `<progress-beacon>\s*(\{.*?\})\s*</progress-beacon>` (multiline, non-greedy).
6. For each match, attempt to parse the captured JSON. Skip if parse fails or any required field (`kind`, `eta_seconds`, `summary`, `drift`) missing.
7. Track the latest by `entry.timestamp` (ISO 8601 → epoch).
8. Return `Some((beacon, timestamp))` or `None`.

Output:

```rust
let now = current_unix_seconds();
let (beacon, emitted_at) = match find_latest_beacon(&path) {
    Some((b, t)) => (Some(b), Some(t)),
    None => (None, None),
};
let age = emitted_at.map(|t| now - t);
println!("{}", json!({
    "beacon": beacon,
    "emitted_at": emitted_at,
    "age_seconds": age,
    "elapsed_ms": elapsed_ms,
}));
```

- [ ] **Step 7: Run conformance — beacons-latest assertions should pass for all 4 latest fixtures**

```bash
cargo build --release && python ../shared/conformance.py --impl rust
```
Expected: all `beacons-latest` assertions pass; `beacons-history` still fails (next task).

- [ ] **Step 8: Commit**

```bash
cd C:/Users/mtsch/claude-walker
git add rust/src/main.rs rust/src/beacons.rs rust/Cargo.toml
git commit -m "feat(rust): implement beacons-latest"
```

### Task 1.5: Implement `beacons-history` + `bias_factor` in Rust

**Files:**
- Modify: `C:/Users/mtsch/claude-walker/rust/src/beacons.rs`

- [ ] **Step 1: Implement `run_history` arg parsing**

Parse `--period` (required), `--win-start` (optional, default to `now - period`), `--projects-root`, `--now`. Compute the time-range filter `[max(now-period, win_start), ∞)`.

- [ ] **Step 2: Implement transcript walk for begin/end pairs**

Glob all `<projects-root>/*/*.jsonl` AND `<projects-root>/*/*/subagents/agent-*.jsonl`. Group by `(parent_dir_name, session_id)` (same grouping as cost mode). For each group:

1. Walk lines, find ALL beacons (same regex + parse logic as latest).
2. Filter to those within the time window.
3. If group has both a `kind: "begin"` and a `kind: "end"`, emit a pair: `(begin.eta_seconds, end.timestamp - begin.timestamp)`.
4. Skip groups missing either side.

- [ ] **Step 3: Implement `bias_factor` median**

```rust
fn bias_factor(pairs: &[(f64, f64)]) -> Option<f64> {
    if pairs.is_empty() { return None; }
    let mut ratios: Vec<f64> = pairs.iter().map(|(b, a)| a / b).collect();
    ratios.sort_by(|x, y| x.partial_cmp(y).unwrap());
    let n = ratios.len();
    Some(if n % 2 == 1 { ratios[n / 2] } else { (ratios[n/2 - 1] + ratios[n/2]) / 2.0 })
}
```

- [ ] **Step 4: Format output**

```rust
println!("{}", json!({
    "pairs": pairs.iter().map(|(b, a)| json!({"begin_eta": b, "actual_elapsed": a})).collect::<Vec<_>>(),
    "session_count": session_count,
    "n_pairs": pairs.len(),
    "bias_factor": bias_factor(&pairs),
    "elapsed_ms": elapsed_ms,
}));
```

- [ ] **Step 5: Run full conformance — all beacon assertions should pass**

```bash
cargo build --release && python ../shared/conformance.py --impl rust
```
Expected: ALL assertions pass for Rust (cost + beacons-latest + beacons-history).

- [ ] **Step 6: Commit**

```bash
git add rust/src/beacons.rs
git commit -m "feat(rust): implement beacons-history + bias_factor"
```

---

## Phase 2: Fan out beacon mode to C++, Go, Zig (parallel subagents)

Goal: bring all four language impls to conformance. Dispatch parallel subagents — one per language — using subagent-driven-development.

### Task 2.1: Pre-dispatch readiness check

- [ ] **Step 1: Verify Rust is the green reference**

```bash
cd C:/Users/mtsch/claude-walker
python shared/conformance.py --impl rust
```
Expected: all assertions pass. If anything is red, fix before dispatching.

- [ ] **Step 2: Allowlist check for parallel subagents**

Per the user's global CLAUDE.md (Permissions section), parallel subagents need `Bash(*)` and `Edit(**)` to be productive. Check `~/.claude/settings.json` (worktrees) and `C:/Users/mtsch/claude-walker/.claude/settings.local.json` (project). If narrow, propose adding the broad grants before dispatch.

```bash
cat ~/.claude/settings.json | grep -A3 '"permissions"' | head -20
cat C:/Users/mtsch/claude-walker/.claude/settings.local.json 2>/dev/null
```

If grants are narrow, ASK the user before broadening.

### Task 2.2: Dispatch parallel subagents (C++, Go, Zig)

Use `superpowers:dispatching-parallel-agents` patterns: 3 isolated worktrees, one per language, each handed the conformance contract + Rust impl as a reference.

- [ ] **Step 1: Create worktrees**

```bash
cd C:/Users/mtsch/claude-walker
git worktree add ../claude-walker-cpp -b beacons-cpp main
git worktree add ../claude-walker-go -b beacons-go main
git worktree add ../claude-walker-zig -b beacons-zig main
```

- [ ] **Step 2: Dispatch subagents in a single Agent tool message (parallel)**

Each subagent gets:
- Working directory: its worktree
- Reference: `rust/src/beacons.rs` (Rust impl)
- Reference: `SPEC.md` (subcommand contracts)
- Reference: `shared/corpus/beacons/` (fixtures)
- Reference: `shared/conformance.py` (assertion contract)
- Acceptance criterion: `python shared/conformance.py --impl <lang>` passes ALL assertions including new beacon ones.
- Constraint: do not modify Rust impl, fixtures, conformance.py, or SPEC.md. Only implement in the assigned language directory.

Prompt template (per language):

> You are implementing the `beacons-latest` and `beacons-history` subcommands in the `<lang>` impl of claude-walker. The Rust reference at `rust/src/beacons.rs` defines the algorithm; the conformance harness (`python shared/conformance.py --impl <lang>`) defines acceptance. Modify only the `<lang>/` directory. When all conformance assertions pass, commit on the `beacons-<lang>` branch with message `feat(<lang>): implement beacons subcommands` and report back.

- [ ] **Step 3: Wait for subagents, review each one's diff**

After all three return:
- For each: run `python shared/conformance.py --impl <lang>` in the worktree.
- For each: review the diff (`git diff main..beacons-<lang> -- <lang>/`).

- [ ] **Step 4: Merge each branch back to main (skills-dev convention: Gitea origin, GitHub mirror)**

```bash
cd C:/Users/mtsch/claude-walker
git checkout main
git merge beacons-cpp --no-ff -m "merge: cpp beacons impl"
git merge beacons-go --no-ff -m "merge: go beacons impl"
git merge beacons-zig --no-ff -m "merge: zig beacons impl"
git worktree remove ../claude-walker-cpp
git worktree remove ../claude-walker-go
git worktree remove ../claude-walker-zig
git branch -d beacons-cpp beacons-go beacons-zig
```

- [ ] **Step 5: Final cross-language conformance**

```bash
python shared/conformance.py --impl all
```
Expected: all 4 impls pass all assertions, byte-identical JSON output.

---

## Phase 3: Production install of claude-walker

### Task 3.1: Pick canonical binary install mechanism

- [ ] **Step 1: Decide install path**

C++ binary lands at `~/.local/bin/claude-walker` on Linux/Git-Bash. Hook + status line invoke `claude-walker` by name (PATH lookup).

- [ ] **Step 2: Add `install.sh` to claude-walker root**

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/cpp"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j
mkdir -p "$HOME/.local/bin"
cp build/walker "$HOME/.local/bin/claude-walker"
echo "installed claude-walker to $HOME/.local/bin/claude-walker"
"$HOME/.local/bin/claude-walker" cost --period 86400 --win-start 0 >/dev/null && echo "smoke test ok"
```

- [ ] **Step 3: Add Windows-friendly `install.bat`**

Equivalent .bat that builds via cmake on Windows and copies to `%USERPROFILE%\.local\bin\claude-walker.exe`. The user adds `%USERPROFILE%\.local\bin` to `PATH` via `setx PATH "%PATH%;%USERPROFILE%\.local\bin"` if not already present (script checks and prompts).

- [ ] **Step 4: Verify by running the install**

```bash
bash install.sh
which claude-walker
claude-walker cost --period 86400 --win-start 0
```

- [ ] **Step 5: Commit**

```bash
git add install.sh install.bat
git commit -m "feat: install scripts for production C++ binary"
```

---

## Phase 4: schoen-claude-status integration

### Task 4.1: Add beacon parsing helpers to `statusline_lib.py`

**Files:**
- Modify: `C:/Users/mtsch/schoen-claude-status/statusline_lib.py`

- [ ] **Step 1: Add `format_beacon` helper**

After the existing format_* helpers, add. Returns `(rendered_str, beacon_dict)` so callers can derive `eta_seconds` for the calibrated line without a second walker call.

```python
def format_beacon(session_id):
    """Returns (rendered_str | None, beacon_dict | None)."""
    try:
        result = subprocess.run(
            ["claude-walker", "beacons-latest", "--session-id", session_id],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0:
            return (None, None)
        data = _json_loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return (None, None)

    beacon = data.get("beacon")
    age = data.get("age_seconds")
    if beacon is None:
        return (None, None)
    if beacon.get("kind") == "end":
        return (None, None)

    if age is not None and age > 300:
        return (f"{RED}⏱ stale {int(age // 60)}m{RESET}", beacon)

    drift = beacon.get("drift", "nominal")
    color = {"nominal": GREEN, "moderate": YELLOW, "material": RED}.get(drift, RESET)
    eta_min = max(1, int(beacon["eta_seconds"] // 60))
    summary = beacon["summary"][:60]
    return (f"{color}⏱ ~{eta_min}m · {summary}{RESET}", beacon)
```

- [ ] **Step 2: Add `format_calibrated_eta` helper**

```python
def format_calibrated_eta(raw_eta_seconds, period_seconds=604800):
    """Calls claude-walker beacons-history, returns calibrated string or None."""
    try:
        result = subprocess.run(
            ["claude-walker", "beacons-history", "--period", str(period_seconds)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        data = _json_loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None

    n = data.get("n_pairs", 0)
    bias = data.get("bias_factor")
    if n < 20 or bias is None:
        return None

    calibrated_seconds = raw_eta_seconds * bias
    cal_min = max(1, int(calibrated_seconds // 60))
    return f"~{cal_min}m calibrated ({bias:.1f}×)"
```

- [ ] **Step 3: Run an eyeball test (no test framework here yet)**

```bash
cd C:/Users/mtsch/schoen-claude-status
python -c "from statusline_lib import format_beacon; print(repr(format_beacon('nonexistent')))"
```
Expected: prints `(None, None)` (cleanly handles missing session).

- [ ] **Step 4: Commit**

```bash
git add statusline_lib.py
git commit -m "feat(lib): format_beacon + format_calibrated_eta helpers"
```

### Task 4.2: Wire beacon column into `statusline.py`

**Files:**
- Modify: `C:/Users/mtsch/schoen-claude-status/statusline.py`

- [ ] **Step 1: Read statusline.py to understand line composition**

Run: `cat statusline.py`. Find where line 2 (`ctx | cache | quota | cost`) is composed; we'll append a beacon column.

- [ ] **Step 2: Import beacon helpers**

Add to imports:

```python
from statusline_lib import (
    format_beacon,
    format_cache,
    format_calibrated_eta,
    format_context,
    format_cost,
    format_quota,
    walk_transcript,
)
```

- [ ] **Step 3: Add beacon column + calibrated line**

Where line 2 is built (look for the existing join of fields), append:

```python
session_id = payload.get("session_id", "")
beacon_str, beacon_dict = format_beacon(session_id) if session_id else (None, None)
if beacon_str:
    line2_fields.append(beacon_str)
```

After printing line 2, conditionally print the calibrated line as line 3:

```python
if beacon_dict and beacon_dict.get("eta_seconds", 0) > 0:
    cal = format_calibrated_eta(beacon_dict["eta_seconds"])
    if cal:
        print(cal)
```

- [ ] **Step 4: Smoke test**

Trigger a render manually:

```bash
echo '{"session_id":"<a-real-session-from-projects-dir>","cwd":"C:/Users/mtsch","model":{"id":"claude-opus-4-7"}}' | python statusline.py
```

Expected: existing line 1 + line 2 fields + (if beacon present) calibrated line. No crash if beacon absent.

- [ ] **Step 5: Commit**

```bash
git add statusline.py statusline_lib.py
git commit -m "feat: render live beacon + calibrated ETA in main statusline"
```

### Task 4.3: Wire beacon column into `subagent_statusline.py`

**Files:**
- Modify: `C:/Users/mtsch/schoen-claude-status/subagent_statusline.py`

- [ ] **Step 1: Read subagent_statusline.py to understand per-row composition**

Run: `cat subagent_statusline.py | head -60`. Note how it loops over `tasks`, builds the `content` string per row.

- [ ] **Step 2: Add beacon column per row**

For each task, the agent's session_id is `agent-<task.id>`. Call `format_beacon(f"agent-{task['id']}")` and append to the row content if non-None.

- [ ] **Step 3: Smoke test**

Same as 4.2 step 6 but with the subagent payload shape (tasks array). Use a synthetic payload to verify rendering.

- [ ] **Step 4: Commit**

```bash
git add subagent_statusline.py
git commit -m "feat: render per-row beacon in subagent statusline"
```

### Task 4.4: End-to-end smoke in a real session

- [ ] **Step 1: Start a fresh Claude Code session in any repo, prompt non-trivially**

E.g., "explore the structure of this repo and summarize." This will fire enough tool calls that even without the skill installed yet, we can verify the status line doesn't break.

- [ ] **Step 2: Confirm status line renders without errors**

The beacon column should be hidden (no skill installed yet), but the rest of the status line must continue to work normally. Watch for stderr leak or rendering glitches.

- [ ] **Step 3: If a render error appears, debug via the input-log dump mechanism**

Per `~/.claude/notes/reference_claude_code_statusline_json.md`, the script writes its stdin to `~/.claude/.statusline-input.log` for inspection. If statusline crashes silently, check that file + stderr for the cause.

---

## Phase 5: skills-progress-beacon skill repo

### Task 5.1: Author SKILL.md body locally in skills-dev

**Files:**
- Create: `C:/Users/mtsch/skills-dev/progress-beacon/SKILL.md` (temporary local dir)

- [ ] **Step 1: Make local working dir**

```bash
mkdir -p C:/Users/mtsch/skills-dev/progress-beacon
```

- [ ] **Step 2: Write SKILL.md**

```markdown
---
name: progress-beacon
description: Use during any non-trivial turn (multi-file edits, multi-step research, planning + implementation, dispatching subagents, or anything you'd ballpark at >2 minutes wall-clock). Periodically emits a `<progress-beacon>` JSON block in the assistant message text so the user's status line can render an ETA. On material drift, surfaces a loud in-line note and continues working — does NOT block the turn for user confirmation.
---

# progress-beacon — agent self-pacing for non-trivial turns

Your user can't tell how long a turn will take. They want a single
visible answer to "can I close my laptop?" — anchored to wall clock.
This skill makes that possible by having you emit a small
machine-readable progress beacon at key moments. The status line
parses it and shows the figure plus a calibrated estimate from
historical sessions.

## When to use this skill

Apply on the FIRST substantive action of any turn that meets ANY
of these criteria:

- The task involves multi-file edits.
- The task involves multi-step research or planning.
- You will dispatch subagents.
- You'd ballpark the turn at >2 minutes of wall-clock work.

If none of those apply (one-line answers, simple Q&A, single-file
lookups, exploratory dialog like brainstorming), the skill is silent
— do not emit a beacon.

## Beacon format

Every beacon is a fenced block in your assistant message text:

\`\`\`
<progress-beacon>
{"kind": "begin", "eta_seconds": 180, "summary": "running tests then committing", "drift": "nominal"}
</progress-beacon>
\`\`\`

Required fields:
- `kind`: `"begin"` | `"report"` | `"end"`.
- `eta_seconds`: wall-clock seconds remaining. Use 0 for `kind: "end"`.
- `summary`: one-line human description, ≤80 chars.
- `drift`: `"nominal"` | `"moderate"` | `"material"`.

Optional:
- `beats_left`: discrete steps remaining (when you have a confident count).

Do NOT include `tokens_left`, `tasks`, or other fields — they're
reserved for future use.

## Lifecycle

- **First substantive action of the turn** → emit `kind: "begin"`
  with your initial estimate. This anchors the original ETA that
  drift is measured against.
- **Periodically during work** → emit `kind: "report"` beacons.
  Cadence is fuzzy ("every so often"), with a HARD BACKSTOP: never
  let more than ~5 minutes of wall-clock pass without a beacon. If
  you notice you've been working without emitting a beacon for what
  feels like a long time, that's the moment to come up for air NOW,
  not at some later "natural" break point.
- **End of substantive work** → emit `kind: "end"` with final
  summary. Status line clears the figure.

## Drift judgement

You decide the drift state, not math. Defaults:

- `nominal`: current `eta_seconds` within 1.5× the original `begin`
  estimate AND total elapsed under 30min.
- `moderate`: 1.5×–2× the original, OR approaching 30min.
- `material`: >2× the original, OR >30min absolute.

When entering `material` drift FROM A NON-MATERIAL STATE
(`nominal → material` or `moderate → material`), prepend a loud
in-line note in your same assistant message:

\`\`\`
🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨

ETA CREEP — was 15min, now looking like 45min.

I'm continuing. **Press ESC and tell me to wrap up** if you'd rather
I call it here and write a handoff.

🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨
\`\`\`

While drift stays `material` on consecutive beacons, do NOT re-flash
the loud note. If drift recovers to `nominal`/`moderate` and later
returns to `material`, the loud note fires again — that's a genuinely
new event worth surfacing.

## What this skill does NOT do

- Does not stop and ask "keep going or wrap?" as a blocking question.
  ETA creep is inform-and-continue. The user's override path is ESC
  + verbal request, not a yes/no prompt.
- Does not prescribe how to compute `eta_seconds`. Honest approach:
  estimate remaining steps × rough seconds/step. Calibration math
  in the status line corrects for systematic bias.
- Does not differentiate orchestrator vs. subagent. Whichever agent
  reads this skill applies it to its own work; the per-row vs.
  main-bar render is a status-line concern, not a skill-body concern.

## Examples

**Trivial turn (no beacon):**
> User: "what does this function do?"
> Agent: [reads file, answers]
> No beacon emitted.

**Non-trivial turn (begin → report → end):**
> User: "refactor the auth middleware to use JWTs"
> Agent: "Plan: read existing middleware, draft new version, update tests, run.
>
> \`\`\`
> <progress-beacon>
> {"kind": "begin", "eta_seconds": 720, "summary": "auth middleware JWT refactor", "drift": "nominal"}
> </progress-beacon>
> \`\`\`
> [reads files, writes new code, runs tests]"
>
> Agent (5 minutes later, after writing new middleware): "Tests are running.
> \`\`\`
> <progress-beacon>
> {"kind": "report", "eta_seconds": 240, "summary": "tests running, ~4 min left", "drift": "nominal"}
> </progress-beacon>
> \`\`\`"
>
> Agent (final): "Done. Tests pass.
> \`\`\`
> <progress-beacon>
> {"kind": "end", "eta_seconds": 0, "summary": "JWT refactor complete, all tests green", "drift": "nominal"}
> </progress-beacon>
> \`\`\`"
```

- [ ] **Step 3: Eyeball check**

Read the SKILL.md back. Sanity check on tone, length (~150 lines is right), example clarity.

### Task 5.2: Author the recency-nudge hook

**Files:**
- Create: `C:/Users/mtsch/skills-dev/progress-beacon/hooks/recency-nudge.sh`

- [ ] **Step 1: Write hooks/recency-nudge.sh**

```bash
#!/usr/bin/env bash
# PostToolUse hook: nudge the agent if no beacon has been emitted recently.
# Reads hook stdin (Claude Code provides JSON), shells out to claude-walker,
# decides whether to inject additionalContext.
set -euo pipefail

input="$(cat)"
session_id="$(printf '%s' "$input" | jq -r '.session_id // empty')"
[[ -z "$session_id" ]] && { echo '{}'; exit 0; }

walker_out="$(claude-walker beacons-latest --session-id "$session_id" 2>/dev/null || true)"
[[ -z "$walker_out" ]] && { echo '{}'; exit 0; }

beacon="$(printf '%s' "$walker_out" | jq -c '.beacon // null')"
age="$(printf '%s' "$walker_out" | jq -r '.age_seconds // empty')"

# Count tool-use entries this turn — used for "no beacon yet" backstop.
# Approximate via count of assistant messages with tool_use content blocks
# in the active transcript. For v1, we trust the >5min staleness path;
# future hardening can refine the no-beacon-ever case.

needs_nudge=0
nudge_msg=""

if [[ "$beacon" == "null" ]]; then
    # No beacon at all — soft case, only nudge if the turn has clearly been
    # going for a while. Skip in v1 if walker can't tell us turn duration;
    # rely on staleness path instead.
    :
else
    kind="$(printf '%s' "$beacon" | jq -r '.kind')"
    if [[ "$kind" != "end" && -n "$age" && "$age" != "null" ]]; then
        # bash float comparison via awk
        if awk -v a="$age" 'BEGIN{exit !(a > 300)}'; then
            needs_nudge=1
            nudge_msg="No progress beacon emitted in $((${age%.*} / 60))+ minutes. If this turn is non-trivial, please emit a <progress-beacon> 'report' now."
        fi
    fi
fi

if [[ "$needs_nudge" -eq 1 ]]; then
    jq -n --arg msg "$nudge_msg" '{
        hookSpecificOutput: {
            hookEventName: "PostToolUse",
            additionalContext: $msg
        }
    }'
else
    echo '{}'
fi
```

- [ ] **Step 2: Make executable + smoke test**

```bash
chmod +x C:/Users/mtsch/skills-dev/progress-beacon/hooks/recency-nudge.sh
echo '{"session_id":"nonexistent"}' | bash C:/Users/mtsch/skills-dev/progress-beacon/hooks/recency-nudge.sh
```
Expected: `{}` printed (no nudge, since walker returns no beacon).

### Task 5.3: Author evals

**Files:**
- Create: `C:/Users/mtsch/skills-dev/progress-beacon/evals/runner.py`
- Create: `C:/Users/mtsch/skills-dev/progress-beacon/evals/README.md`

- [ ] **Step 1: Write minimal eval runner stub**

For v1 we ship the eval scaffolding but the actual grader is a follow-up. The stub:

```python
"""Eval runner for progress-beacon. v1: scaffolding only."""
import argparse, sys

EVAL_CASES = [
    {"id": "trigger-trivial", "prompt": "what is 2+2?", "expect_beacon": False},
    {"id": "trigger-nontrivial", "prompt": "refactor auth.py to use JWT", "expect_beacon": True},
    {"id": "drift-engineered", "prompt": "fix the bug in this function (with hidden 5x scope)", "expect_drift": "material"},
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for c in EVAL_CASES:
            print(f"{c['id']}: {c['prompt']}")
        return
    print("eval runner not yet wired to claude — see evals/README.md", file=sys.stderr)
    sys.exit(2)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write evals/README.md explaining the v1 scaffolding-only state and v2 plan**

### Task 5.4: Author top-level README

**Files:**
- Create: `C:/Users/mtsch/skills-dev/progress-beacon/README.md`

- [ ] **Step 1: Write README.md**

Cover: purpose, install (skill + claude-walker beacon mode + schoen-claude-status patches required), wire format, hook configuration snippet for `~/.claude/settings.json`, link to the design spec history (git ref).

### Task 5.5: Create Gitea + GitHub repos and convert to submodule

Follow the workflow in skills-dev's CLAUDE.md → "Adding a new skill" section. Detailed steps live in `~/.claude/projects/C--Users-mtsch-skills-dev/memory/reference_gitea_submodule_workflow.md`.

- [ ] **Step 1: Create Gitea repo `schoen/skills-progress-beacon`** (use `~/.gitea-token`, the admin token)

- [ ] **Step 2: Create GitHub repo `mtschoen/skills-progress-beacon`** (`gh repo create mtschoen/skills-progress-beacon --public`)

- [ ] **Step 3: Init the local dir as git, commit (with `user.name=claude-code`), push to Gitea**

- [ ] **Step 4: Remove the local dir** (`cd ..` first to avoid Windows busy-cwd error)

- [ ] **Step 5: Add as submodule using absolute Gitea URL, then rewrite `.gitmodules` to relative form** (per the sequencing-pitfall note in the umbrella CLAUDE.md)

- [ ] **Step 6: Configure per-submodule remotes (origin → Gitea SSH, github → GitHub SSH); push to GitHub**

- [ ] **Step 7: Confirm `install-skills.sh -n progress-beacon` (dry run) picks it up**

- [ ] **Step 8: Commit submodule pointer in skills-dev**

- [ ] **Step 9: Run `scripts/push-all.{sh,bat}`** to push everything to both hosts.

### Task 5.6: Wire hook into `~/.claude/settings.json`

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: Add PostToolUse hook entry**

In the `hooks` block of `~/.claude/settings.json` (create if missing), add:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/skills/progress-beacon/hooks/recency-nudge.sh"
          }
        ]
      }
    ]
  }
}
```

If `hooks` block exists, merge carefully — preserve other entries.

- [ ] **Step 2: Verify settings.json is still valid JSON**

```bash
jq . ~/.claude/settings.json >/dev/null && echo "ok"
```

---

## Phase 6: Real-session shake-down

### Task 6.1: Install everything end-to-end

- [ ] **Step 1: Verify claude-walker is on PATH**

```bash
which claude-walker
claude-walker beacons-latest --session-id any
```
Expected: returns `{"beacon": null, ...}` (no error).

- [ ] **Step 2: Verify skill is installed**

```bash
ls ~/.claude/skills/progress-beacon/
```
Expected: SKILL.md + hooks/ + evals/ + README.md.

- [ ] **Step 3: Verify schoen-claude-status patches are live**

The user's `settings.json` already points at `~/schoen-claude-status/statusline-command.sh`. Modifying the .py files there is the live update — no symlinking needed. Trigger any Claude Code render (open a session, glance at status line). Expected: no error; beacon column hidden until the agent emits one.

### Task 6.2: First real session — confirm beacon emits + renders

- [ ] **Step 1: Start a fresh Claude Code session and prompt with a non-trivial task**

E.g., "investigate why the test suite is slow and propose three improvements."

- [ ] **Step 2: Watch for the begin beacon in the agent's first response**

Visually scan: is there a `<progress-beacon>` block? If not, the skill didn't fire — capture transcript path for diagnostics.

- [ ] **Step 3: Watch the status line**

Expected: `⏱ ~Nm · summary` appears tinted green (nominal). If `n_pairs >= 20` already (unlikely on first run), calibrated line below.

- [ ] **Step 4: Watch for periodic report beacons**

If the turn runs >5 minutes without a `report`, the recency-nudge hook should fire and inject a system-reminder. Verify via either the agent visibly emitting a beacon shortly after the threshold, or by checking transcript for the additionalContext injection.

### Task 6.3: Open observation log

**Files:**
- Create: `~/.claude/notes/project_progress_beacon.md`
- Modify: `~/.claude/notes/MEMORY.md`

- [ ] **Step 1: Write project_progress_beacon.md**

```markdown
---
name: progress-beacon real-session shake-down
description: Observation log during v1 shake-down of the progress-beacon skill. Track: under-trigger cases, over-trigger / nag cases, calibration convergence, material-drift signal-to-noise.
type: project
---

## Setup
- Installed YYYY-MM-DD on chonkers.
- claude-walker C++ binary at `~/.local/bin/claude-walker`.
- Skill at `~/.claude/skills/progress-beacon/`.
- Hook configured in `~/.claude/settings.json` PostToolUse block.

## What we're watching for
- **Under-trigger**: turns where beacon SHOULD have fired but didn't.
- **Over-trigger / nag**: beacons firing on trivial turns, or recency hook nudging too eagerly.
- **Calibration convergence**: does `bias_factor` stabilize over time?
- **Material-drift signal-to-noise**: does the loud note fire when warranted, stay silent otherwise?

## Sessions

### YYYY-MM-DD — [session topic]
- Beacons emitted: N
- Drift transitions: ...
- Calibration n_pairs at session start: N
- Calibration n_pairs at session end: N
- bias_factor at session start: X.XX
- bias_factor at session end: X.XX
- Notes: ...

(Append entries here as we go.)
```

- [ ] **Step 2: Add MEMORY.md pointer**

Append to `~/.claude/notes/MEMORY.md`:

```
- [progress-beacon shake-down](project_progress_beacon.md) — v1 install YYYY-MM-DD; watching for under/over-trigger and calibration convergence
```

### Task 6.4: Fix the stale memory note ambiguity

**Files:**
- Modify: `~/.claude/notes/reference_claude_code_statusline_json.md` (line 107–108)

- [ ] **Step 1: Update the ambiguous "in this repo" reference**

Change "The live statusline-command.sh in this repo writes that dump on every render" → "The live statusline-command.sh in `~/schoen-claude-status/` writes that dump on every render".

- [ ] **Step 2: Commit (memory dirs aren't usually under git, but if they are):**

```bash
cd ~/.claude/notes && git add reference_claude_code_statusline_json.md && git commit -m "docs: clarify schoen-claude-status path"
```

(Skip commit if memory dir isn't a git repo.)

---

## Plan complete. Acceptance checks before declaring v1 done

- [ ] All four claude-walker impls pass full conformance (cost + beacons-latest + beacons-history).
- [ ] `claude-walker` on PATH on chonkers.
- [ ] Skill installed at `~/.claude/skills/progress-beacon/`.
- [ ] PostToolUse hook configured in `~/.claude/settings.json`.
- [ ] schoen-claude-status patches landed and live.
- [ ] At least one real session exercised the lifecycle (begin → report → end) end-to-end with the status line rendering correctly.
- [ ] Observation log opened at `~/.claude/notes/project_progress_beacon.md`.
- [ ] Stale memory-note ambiguity fixed.

After these are green, the v1 implementation is shipped. v2 work (cross-row aggregation, per-task-type calibration, confidence intervals, structured logs, `tokens_left` field) lives in follow-up specs/plans, not this one.
