# `progress-beacon` skill — design

**Status:** draft, brainstormed 2026-05-10
**Author:** mtschoen + Claude (brainstorming session)
**Repos affected (three-repo coordinated change):**
- `skills-progress-beacon/` (new) — SKILL body, recency-nudge hook, README
- `~/claude-walker/` — gains `beacons-latest` and `beacons-history` subcommands across all four language impls (Rust → C++ → Go → Zig)
- `~/schoen-claude-status/` — `statusline.py` + `subagent_statusline.py` patches to render beacon + calibrated ETA

**Deploy target:** `~/.claude/skills/progress-beacon/`
**Publish target:** Gitea `schoen/skills-progress-beacon` + GitHub `mtschoen/skills-progress-beacon`

## Purpose

Agentic coding sessions today give the user no way to predict how long a turn will take. A "five-minute" plan can quietly run an hour. A two-minute fix can return in seconds. The user can't tell when to close the laptop, sleep the machine, or context-switch.

`progress-beacon` introduces a structured "come up for air" beat: the agent periodically emits a small, machine-readable beacon describing its current ETA and a human-readable summary, which the status line picks up and renders. When the agent's own estimate drifts materially from its first call, the agent flags it loudly in the in-line response so the user can ESC and call for a wrap if they want.

The user's load-bearing question — *"can I close my laptop?"* — collapses to a single number visible at all times, with calibration math correcting for the agent's known unreliability at self-estimating wall-clock.

## Non-goals

- **Not a blocking confirmation flow.** The agent never stops to ask "keep going or wrap?" mid-stream. ETA creep is reframed as inform-and-continue. The user's override path is ESC + verbal request, not a yes/no prompt the agent waits on. *(Reasoning: Claude Code's Notification hooks cannot synthesize a user response after a timeout, so any "block then auto-resume after AFK" implementation requires hacking around missing harness primitives. Inform-and-continue avoids the halt-on-AFK failure mode without depending on those primitives.)*
- **Not a token-spend predictor.** Token-remaining estimates are explicitly out of scope for v1 — that's the predictive cost work `/cost-estimator` hasn't yet built. The beacon's optional `tokens_left` field is reserved for v2.
- **Not stateful across sessions, except via calibration.** The skill itself doesn't maintain durable per-session state. The only cross-session memory is the bias factor computed from historical `(begin_eta, actual_elapsed)` pairs by `claude-walker beacons-history`.
- **Not a replacement for plan-execution X/Y UI.** Claude Code already shows X/Y task progress when executing a plan. The beacon is for the wider class of non-plan turns where no such progress exists today.
- **Not coupled to PushNotification.** PushNotification doesn't traverse SSH cleanly, which the user often uses. Loud in-line emphasis (emoji + bangs) on first entry to material drift is the attention-grabber instead.

## Architecture overview

Three artifacts span three repos, communicating through one shared on-disk format (the beacon, embedded in transcript JSONLs).

```
┌───────────────────────────────────────────────────────────────┐
│  skills-progress-beacon/                                       │
│    SKILL.md                — agent-facing rules                │
│    hooks/recency-nudge.sh  — PostToolUse: nudge if stale       │
│    README.md, evals/                                           │
└───────────────────────────────────────────────────────────────┘
           │                            │
           │ emits beacons              │ shells out to
           │ in transcript              │ claude-walker
           ▼                            ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│  Claude Code transcript JSONL│   │  ~/claude-walker             │
│  ~/.claude/projects/<slug>/  │   │    rust/  cpp/  go/  zig/    │
│    <session>.jsonl           │   │    new subcommands:          │
│    subagents/agent-*.jsonl   │◄──│      beacons-latest          │
└──────────────────────────────┘   │      beacons-history         │
                                   └──────────────────────────────┘
                                                │
                                                │ stdout JSON
                                                ▼
                                   ┌──────────────────────────────┐
                                   │  ~/schoen-claude-status      │
                                   │    statusline.py             │
                                   │    subagent_statusline.py    │
                                   │    renders ⏱ + calibrated ETA│
                                   └──────────────────────────────┘
```

**Why beacon-as-fenced-block-in-assistant-text:** keeps the beacon in the natural conversation flow (no separate IPC layer), survives compaction (it's text), automatically per-session (each transcript is its own file), and lets the user visually see when beacons fire — a small social-pressure check on the agent's discipline.

**Why claude-walker as the parser:** it already walks the transcript fleet at native speed (target 30–80ms for a week), already groups by `(slug, session_id)`, already does mtime-pruning. Adding beacon extraction as a subcommand reuses all that machinery and inherits its conformance harness. The hook + status line both call the same binary, eliminating drift between consumers.

**Why C++ canonical:** C++ has been the perf winner across the existing claude-walker impls. Production hook + status line invoke `claude-walker` which (post-distribution, exact mechanism TBD) routes to the C++ binary. Other-language ports stay conformance-tested for parity.

## Wire format

The beacon is a fenced block in the agent's assistant message text:

```
<progress-beacon>
{"kind": "begin", "eta_seconds": 180, "summary": "running tests then committing", "drift": "nominal"}
</progress-beacon>
```

### Required fields

| Field         | Type   | Values                                              | Purpose |
| ------------- | ------ | --------------------------------------------------- | ------- |
| `kind`        | string | `"begin"` / `"report"` / `"end"`                    | LSP-aligned lifecycle. `begin` is the first beacon of a substantive turn (anchors the original estimate). `report` is mid-turn. `end` marks completion. |
| `eta_seconds` | number | seconds remaining (0 for `kind: "end"`)             | The load-bearing wall-clock figure rendered in the status line. |
| `summary`     | string | one-line human description, ≤80 chars               | Rendered alongside the time figure: `⏱ ~3m · running tests then committing`. |
| `drift`       | string | `"nominal"` / `"moderate"` / `"material"`           | Agent's semantic call. Drives status line tinting (green/yellow/red) and the loud in-line note on first entry to `material`. |

### Optional fields

| Field         | Type   | When present | Purpose |
| ------------- | ------ | ------------ | ------- |
| `beats_left`  | number | when the agent has a confident discrete-step count | Rendered as `· 3 left` after the summary. Omitted otherwise; status line just doesn't render that column. |

`tokens_left`, `tasks` (X/Y), and similar are deferred to v2 (see *Future work* below). v1 stays minimal.

### Drift thresholds (defaults; v1 hardcoded)

- **`nominal`** — current `eta_seconds` is within 1.5× the original `begin` `eta_seconds` AND total elapsed remains under 30min absolute.
- **`moderate`** — between 1.5× and 2× the original, OR approaching 30min. Status line tints yellow, no escalation.
- **`material`** — exceeds 2× the original, OR exceeds 30min absolute. Status line tints red. **Each entry into this state from a non-material state** triggers the loud in-line note (so `nominal → material` flashes; `moderate → material` flashes; but `material → material` on consecutive beacons does *not* re-flash). If drift recovers to `nominal`/`moderate` and later returns to `material`, the loud note fires again — that's a genuinely new event worth surfacing.

### Loud in-line note (first entry to material drift)

The agent emits something like:

```
🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨

ETA CREEP — was 15min, now looking like 45min.

I'm continuing. **Press ESC and tell me to wrap up** if you'd
rather I call it here and write a handoff.

🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨
```

Exact emoji and formatting handled in SKILL.md examples — calibrate so it stands out against normal output but doesn't become annoying when re-triggered (which is why repeat-in-state is silent).

## SKILL.md body shape

### Trigger / scope (when does the skill apply at all?)

The agent uses this skill at the start of any turn it judges as non-trivial — multi-file edits, multi-step research, planning + implementation, dispatching subagents, anything the agent itself would ballpark at >2 minutes wall-clock. For one-line answers, single-file lookups, and simple Q&A, the skill is silent (no beacon emitted).

### Lifecycle

- **First substantive action** → `kind: "begin"` beacon with `eta_seconds`, `summary`, `drift: "nominal"`. Anchors the original estimate; subsequent drift is measured against this number.
- **Periodically during work** → `kind: "report"` beacons. Cadence is fuzzy ("every so often"), with a hard backstop: never more than ~5 minutes of wall-clock without a beacon. The recency-nudge hook also enforces this from the harness side.
- **Material drift first entry** → emit `kind: "report"` with `drift: "material"` AND prepend the loud in-line note in the same assistant message. Continue working.
- **Material drift continued** → subsequent beacons keep `drift: "material"`, but no repeat of the loud note. Status line stays red.
- **End of substantive work** → `kind: "end"` with final `summary`. Status line clears the figure.

### Drift judgement

The `drift` value is the agent's call, not a math computation. The agent reads its prior beacons from the transcript (or its own context) and decides whether the latest estimate has drifted enough to warrant escalation. Defaults above (1.5× / 2× / 30min) are a guideline; if the agent has reason to override (e.g., remaining work is tightly bounded so absolute elapsed is misleading), it can.

### Self-application clause

Explicit instruction in SKILL.md, written specifically against the failure mode documented in `feedback_skill_self_application.md`:

> If you notice you've been working without emitting a beacon for what feels like a long time — that's the moment to come up for air *now*, not at some later 'natural' break point. The user is waiting on this signal.

### What the skill does NOT do

- Does not tell the agent how to compute the wall-clock estimate. (Honest take: agent estimates remaining steps × rough seconds/step. Calibration is poor early; gets corrected by the bias-factor math at the status line layer.)
- Does not differentiate orchestrator vs. subagent in the body. The skill applies to whichever agent is reading it. Per-row vs. main-bar rendering is a status-line concern, not a skill-body concern.
- Does not instruct the agent to ask "keep going or wrap?" as a blocking question (see *Non-goals*).

## Recency-nudge hook (`hooks/recency-nudge.sh`)

**Event:** `PostToolUse` (any tool — runs after every tool result during the agent's turn).

**Logic:**

1. Read transcript path + session_id from hook stdin.
2. Shell out: `claude-walker beacons-latest --session-id "$session_id"`.
3. Parse `age_seconds`. If:
   - No beacon at all + >10 tool calls into the turn → return `additionalContext` nudge ("emit a `begin` beacon now if this turn is non-trivial").
   - `age_seconds > 300` AND `kind != "end"` → return `additionalContext` nudge ("no beacon in 5+ minutes, emit a `report`").
   - Otherwise → silent (return no `additionalContext`).

**Cheapness guarantees:**
- claude-walker's mtime-prune skips ~80% of historical files; with `--session-id`, only one transcript is considered.
- Hook execution should stay well under 100ms per tool call.

**Convenient byproduct:** PostToolUse only fires when tools are used. Trivial Q&A turns (no tool calls) never trigger the hook. The skill's self-gating worry is partly mooted by hook lifecycle.

## Status line render (schoen-claude-status patches)

### `statusline.py` (main bar)

Add a beacon column. On each render:

1. `claude-walker beacons-latest --session-id <id>` for live figure.
2. `claude-walker beacons-history --period 604800` (last 7d) for `bias_factor`.
3. Render:
   - Beacon found, fresh (<5min): `⏱ ~Nmin · summary` tinted by `drift` (green/yellow/red).
   - Beacon found, stale (>5min, not `end`): `⏱ stale 6m` in red — visible signal that the figure is untrustworthy. Pairs with the hook's nudge.
   - No beacon, or `kind: "end"`: column is hidden.
4. Calibrated line below (only when `n_pairs >= 20`):
   - `~17min calibrated (1.7×)`
   - Below threshold or no beacon: line omitted. No fake confidence.

### `subagent_statusline.py` (per-task rows)

Same logic against each task's own JSONL. Each subagent's session_id is `agent-<id>` (already in the per-task hook payload). Renders the beacon in the per-task row alongside existing token/cost columns.

**Aggregate question (does main bar combine subagent ETAs?)** → defer to v2. v1: main bar shows orchestrator's own beacon; subagent rows show their own. No cross-row aggregation in v1.

### `statusline_lib.py` (shared)

Beacon parsing and rendering helpers extracted here so both consumers share code. Pure Python — claude-walker is the data source, this layer just formats.

## claude-walker beacon mode

### CLI shape

claude-walker grows two new subcommands. The bare invocation (existing cost-summing behavior) becomes `claude-walker cost`. Backwards compatibility for the no-subcommand form is not preserved — claude-walker is 10 minutes old and has no external consumers yet.

#### `claude-walker beacons-latest --session-id <id> [--projects-root <path>]`

For the hook + status line. Walks the single matching transcript, finds the most recent assistant message containing a `<progress-beacon>` block.

Output (one JSON line on stdout, exit 0; matches existing claude-walker convention):

```json
{
  "beacon": {
    "kind": "report",
    "eta_seconds": 240,
    "summary": "tests still running",
    "drift": "moderate",
    "beats_left": 2
  },
  "emitted_at": 1746816900.123,
  "age_seconds": 142,
  "elapsed_ms": 12
}
```

If no beacon found:

```json
{"beacon": null, "elapsed_ms": 8}
```

#### `claude-walker beacons-history --period <seconds> [--win-start <unix>] [--projects-root <path>]`

For calibration. Walks the full fleet under the time window, extracts every `(begin_eta, actual_elapsed)` pair across all sessions where a `begin` and a corresponding `end` were both present.

Output:

```json
{
  "pairs": [
    {"begin_eta": 600, "actual_elapsed": 1020},
    {"begin_eta": 300, "actual_elapsed": 280},
    ...
  ],
  "session_count": 47,
  "n_pairs": 124,
  "bias_factor": 1.68,
  "elapsed_ms": 64
}
```

`bias_factor` is the median of `actual_elapsed / begin_eta` across all pairs. Consumer (status line) reads it directly.

### Multi-language scope

All four languages (Rust, C++, Go, Zig) implement both subcommands. Conformance harness (`shared/conformance.py`) gains beacon fixtures asserting cross-language parity. Fan-out order:

1. **Rust first** — reference impl (most-comfortable starting point).
2. **C++ next** — production target (perf winner; the binary the hook + status line actually invoke).
3. **Go + Zig** — parallel fan-out via subagents once the spec is locked.

### Conformance fixtures

Beacon fixtures live in `shared/corpus/beacons/`:

- `clean-begin-report-end.jsonl` — straightforward lifecycle.
- `malformed-json.jsonl` — beacon with broken JSON (must be silently skipped).
- `missing-required-field.jsonl` — partial beacon (must be silently skipped).
- `multiple-beacons-one-turn.jsonl` — return latest by timestamp.
- `cross-session-pairs.jsonl` — fixture for `bias_factor` math with a known expected value.

Conformance assertion: all four impls return byte-identical JSON (modulo `elapsed_ms`).

## Calibration

### Math (v1)

`bias_factor = median(actual_elapsed / begin_eta)` across all `(begin, end)` pairs in the time window.

- Median (not mean) for robustness against tail outliers (one runaway 4-hour session shouldn't dominate).
- Per-pair ratio (not aggregate ratio) because pair-level signal is what we care about.
- Time window: 7 days default (~`604800` seconds). Tunable via `--period`.

### Display

When `n_pairs >= 20` (enough samples for confidence), status line renders both raw and calibrated:

```
⏱ ~10min · running tests then committing
   ~17min calibrated (1.7×)
```

When `n_pairs < 20`, only raw renders. No fake confidence in the calibrated line until we have enough data.

### Verification

Per the user's "checking our work will be essential," v1 includes a debug surface:

- `claude-walker beacons-debug --session-id <id>` — dumps full beacon history for a session: every begin/report/end with timestamps, drift transitions, eta deltas. Lets the user retrospectively audit "was that calibration sensible?"
- Real-session calibration log → freeform `.md` notes at `~/.claude/notes/project_progress_beacon.md` for the v1 shake-down period. Matches the pattern used for `project_pushback_skill.md` qualitative testing. If we find we want structured logging, that's a v2 addition.

## Error handling

| Failure mode | Behavior |
| --- | --- |
| Malformed beacon JSON | Walker silently skips; logs to stderr. Hook + status line treat as "no beacon." |
| Missing required field | Same — silently skipped. |
| Walker fails to invoke (binary missing, panic, hang) | Hook returns no `additionalContext`; status line hides beacon column. Per existing claude-walker spec: "Anything other than exit 0 with a single JSON line on stdout is fall back to caller's reference path." Both consumers fail open. |
| Subagent transcript not yet flushed | Walker sees what's there. If no beacon yet, row just doesn't show one. |
| Unrecognized `drift` value | Treated as `nominal` for status line tinting. Forward-compat for any future drift states. |
| `n_pairs` insufficient for calibration | Calibrated line omitted. Honest. |
| Loud in-line note re-triggers | Driven by the entry-from-non-material rule in the SKILL body (see *Drift thresholds*). Walker can detect "drift transitioned material→material" vs. "non-material→material" between two beacons if we want to enforce from the harness side; v1 trusts the agent. |

## Eval / testing

### claude-walker conformance harness (in claude-walker repo)

Beacon fixtures in `shared/corpus/beacons/` (listed above), all four impls assert identical output. Calibration math fixture has a known expected `bias_factor`.

### Skill-level evals (in skills-progress-beacon repo `evals/`)

- **Trigger eval** — synthetic prompts that should and shouldn't fire a beacon. Pass = beacon emitted iff turn is non-trivial.
- **Initial-estimate ballpark eval** — for prompts with known approximate complexity, assert the agent's `begin` `eta_seconds` is within an order of magnitude of human estimate.
- **Drift-detection eval** — prompts engineered to take materially longer than initial estimate (deep refactors, ambiguous specs). Pass = agent emits `drift: "material"` and prepends the loud note.
- **Self-application eval** — long-running synthetic task with no natural pause points. Pass = beacons emitted at <5min cadence even when not externally prompted.

### Real-session qualitative log

`~/.claude/notes/project_progress_beacon.md` — observational notes during v1 shake-down. Patterns we're watching for:
- Under-trigger (missing beacons in real sessions) — visible to the user.
- Over-trigger (chatty / nag) — invisible by default; user must actively notice annoyance.
- Calibration convergence — does `bias_factor` stabilize over time, or stay noisy?
- Material-drift signal-to-noise — does the loud note fire when we'd want it to, and stay silent otherwise?

**Design principle (from this brainstorming session):** err on the side of more triggers in v1. Tune down only if real usage shows nag.

## Distribution

### Skill repo (`skills-progress-beacon`)

Per skills-dev convention: relative-URL submodule under skills-dev, mirrored on Gitea (`schoen/skills-progress-beacon`) + GitHub (`mtschoen/skills-progress-beacon`). Root-layout (SKILL.md at root, plus hooks/, evals/, README.md). Installer (`install-skills.{sh,bat}`) picks it up automatically.

### claude-walker binary

Production target (C++) lands on user PATH. Exact mechanism TBD during implementation:
- Option A: `cmake --build && cp build/walker ~/.local/bin/claude-walker`
- Option B: claude-walker repo grows an `install.sh` that picks the canonical impl and installs it.

Hook + status line invoke `claude-walker beacons-latest ...` by name (PATH lookup), no absolute paths.

### schoen-claude-status patches

Land directly in that repo (already user-owned). `settings.json` at `~/.claude/settings.json` already points at `~/schoen-claude-status/statusline-command.sh` and `…/subagent-statusline.sh`; modifying the canonical scripts is the live update.

**Note:** `~/.claude/notes/reference_claude_code_statusline_json.md` line 107–108 ("The live statusline-command.sh in this repo writes that dump on every render") is ambiguous about which repo "this" refers to. Update during the wrap of this session: clarify it means `~/schoen-claude-status/`.

## Future work (v2 candidates)

- **`tokens_left` field** — predictive token-spend, requires the predictive work `/cost-estimator` is planning.
- **Cross-row aggregation in main bar** — when subagents are running, main bar shows aggregate ETA (e.g., `max(self_eta, max(child_eta))`) rather than just orchestrator's own.
- **Calibration by task type** — bias factor varies by what kind of work is being done (refactor vs. test fix vs. spec authoring). Per-type calibration if we can classify turns from the transcript.
- **Confidence intervals on calibrated ETA** — instead of a point estimate, render `~17min ± 5min` where the spread comes from the variance of historical pairs.
- **Structured calibration log** (replacing freeform `.md`) if real-session observation shows we need queryable history.

## Open questions

- **C++ binary distribution mechanism** — TBD during implementation. Need to keep the install painless on Windows + Linux (chonkers + llamabox).
- **Conformance fixtures across languages** — beacon-mode fixtures are new; we should make sure the existing harness machinery extends cleanly.
- **Self-application backstop** — do we want walker to detect "drift transitioned to material between two beacons" and the hook to nudge if no loud note appeared in the agent's text? v1 trusts the agent; flagged as an explicit future hardening.
