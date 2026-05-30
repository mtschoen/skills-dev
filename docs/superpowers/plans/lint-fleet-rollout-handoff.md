# Lint rollout — handoff (2026-05-29)

Session handoff for the skills-dev linting rollout. Branch **`lint-rollout`**
(7 commits, **not pushed**). This file lives under `docs/superpowers/plans/`
which markdownlint ignores.

## DONE — umbrella-scoped lint gate (committed, green)

`lint-rollout` (7 commits, `a7937a7`..`72f5e8e`) ships a working **umbrella-only**
gate. All verified 0-findings / passing locally:

- **ruff** (`pyproject.toml`, pinned 0.15.15) — Python format+lint over `scripts/` + `tests/`. Owns Python format/lint authoritatively.
- **shellcheck** — `scripts/*.sh install-skills.sh tests/test-install.sh`; fixed 2 real bugs (SC2164 `cd || exit` in push-all/pull-all.sh, SC2015 in test-install.sh).
- **aislop** (`.aislop/config.yml`, pinned 0.9.4) — code-quality/ai-slop/architecture/security; `ci.failBelow: 100` **fail-closed verified**; telemetry off; format+lint engines off (ruff owns those). Project-scoped, **never** global.
- **On-save hook** (`.claude/settings.json`, committed via a `.gitignore` negation): `ruff_on_save.py` (ruff `.py` + shellcheck `.sh`) **+** `aislop hook claude`. Advisory, non-blocking.
- **CI** (`.gitea/workflows/lint.yml`): jobs `markdown`, `validate-skills`, `ruff`, `shellcheck`, `aislop`.
- `TEST-REPORT.md` + CLAUDE.md "Linting" section document it all.

Pre-existing, out of scope, surfaced in `TEST-REPORT.md`: 4 `test_install_skills.py`
failures (Windows `install-skills.sh` `.gemini`-harness creation) — proven
pre-existing, not caused by this work.

## TODO — fleet-wide expansion (the "fix the things" the user asked for)

User decision this session: **stop scoping to umbrella; lint submodule code too**
("you can go into the submodules — we won't set this up for each one"). Submodules
are separate git repos, so fixes are committed **inside each submodule (direct to
main, as Matt Schoen), pushed to origin+github, then pointer-bumped** in the
umbrella. User picked execution = **Sonnet agents fix / human pushes** (check the
`.claude/settings.local.json` + global allowlist before dispatch — global
`~/.claude/settings.json` already has `Bash(*)`/`Edit(**)`/`Write(**)`).

### Step 0 — re-apply the scope-widening config (was reverted at wrap to keep the branch green)

These edits were made, then reverted during `/wrap` because committing them
without the fixes would turn CI red. Re-apply:

- `pyproject.toml` `[tool.ruff].exclude`: **remove all 17 submodule dir entries**, keep only the workspace/node_modules/fixtures globs.
- `.aislop/config.yml` `exclude:`: **remove all 17 submodule dir entries**, keep `node_modules/dist/build/.git/**workspace**`.

### Measured findings under our config (fleet-wide)

| Linter | Findings | Notes |
|---|---|---|
| ruff | **67** (52 autofix, ~15 hand) | filesystem-walk already crosses submodules; mostly mechanical (I001, F541, UP045, narrative). Run `ruff check --fix .` + `ruff format .` then hand-fix the rest. |
| shellcheck | **1 file** | `wrap/scripts/find-unwrapped.sh`. |
| markdownlint | **0 real** | The 7 reported are all in `LINTER-SETUP.md` (untracked scaffold). Submodule `SKILL.md`/`references/` are clean. Config already sensible (MD013/MD041/MD060 off). |
| aislop | scores **17–85** per submodule | Real cleanup, NOT autofix. cost-estimator 17, remote-claude 25, fast-tests 71, pushback 85; wrap/smoke-test 100. Examples: `analyze-month.py` `main` is 296 lines (max 80), file 488 lines (max 400); catch-blocks that only `print`; narrative comment blocks; thin wrappers; unused `from __future__ import annotations` (×12 in cost-estimator). |

Affected submodules (have `.py`/`.sh`): cost-estimator, escalate-over-shortcut,
fast-tests, progress-beacon, pushback, remote-claude, review-in-parallel-pipelines,
smoke-test, wrap. (Full per-submodule `.py`/`.sh`/`.md` inventory was taken; cost-estimator has the most: 17 .py.)

### OPEN DECISION (blocks the aislop part) — aislop cleanup depth

Not answered before wrap. Pick one:

- **`ci.failBelow: 100`** everywhere → forces real refactors (split 296-line functions, rewrite catch-blocks) across ~6 repos. Large, judgment-heavy churn on eval/helper scripts.
- **Looser `ci.failBelow` (e.g. 85)** → clears mechanical/auto-fixable slop fleet-wide without forcing big function-splitting refactors. Much smaller.

ruff/shellcheck stay at the strict 0-bar regardless (mechanical).

### How aislop must run fleet-wide (key mechanic — see `~/.claude/notes/reference_aislop.md`)

`aislop ci .` only sees umbrella files (git enumeration stops at submodule
gitlinks). **Give it explicit paths** — `aislop ci <submodule>` globs the
filesystem and DOES scan the submodule, while still applying the umbrella
`.aislop/config.yml` (verified: format/lint stayed off, exit 1 on low score).
So the CI `aislop` job must become a loop:

```bash
fail=0
npx -y aislop@0.9.4 ci || fail=1                       # umbrella
for s in cost-estimator escalate-over-shortcut fast-tests progress-beacon \
         pushback remote-claude review-in-parallel-pipelines smoke-test wrap; do
  npx -y aislop@0.9.4 ci "$s" || fail=1
done
exit $fail
```

CI checkout must use `submodules: recursive` for that job. The on-save hook
already covers submodule files per-edit (it passes the file path; config resolves
from the umbrella root).

### Execution sketch (per affected submodule, via Sonnet agent)

1. `ruff check --fix` + `ruff format` + hand-fix remaining ruff in that submodule.
2. shellcheck fixes (only wrap).
3. aislop cleanup to the chosen `failBelow` (`npx aislop@0.9.4 ci <sub>` from umbrella root to check; `aislop fix` for mechanical, hand-refactor the rest).
4. Commit direct to submodule main as Matt Schoen; **human pushes** origin+github.
5. In umbrella: bump the submodule pointer.
Finally: one umbrella commit bumping all pointers + the re-applied config widening + the CI loop; update `TEST-REPORT.md`.

## Other pending items (never resolved this session)

- **Push + PR**: `lint-rollout` is NOT pushed. Plan was `git push origin lint-rollout` → open PR on Gitea as the **claude-code** bot (so Matt can approve; Gitea blocks self-approval). Leave GitHub mirror until merge. Awaiting go-ahead.
- **`LINTER-SETUP.md`**: untracked scaffold (the original spec). Disposition undecided — delete (rationale folded into CLAUDE.md + TEST-REPORT.md) / leave / commit. It's the only source of the 7 markdownlint findings.
- **markdown on-save hook**: markdown is CI-only; not in `ruff_on_save.py`. Could add a `.md` branch running `markdownlint-cli2` (pinned npx) if symmetry wanted. (aislop doesn't do markdown.)
- **`shellcheck-py`**: pip-installed locally this session for verification (user-space, reversible). Keep (lets you run the shell gate on Windows) or `pip uninstall shellcheck-py`.

## Process notes / corrections made this session

- aislop's `hook install` overreached into global `~/.claude/` (settings.json, CLAUDE.md, AISLOP.md) — **fully reverted and diff-verified**; global config is clean. gemini/codex were never actually modified (`hook status` misreports). Details in `~/.claude/notes/reference_aislop.md`.
- One commit (`374c9e4`) shipped a false "verified fail-closed" claim; the gate didn't actually block until the real `ci.failBelow` key was found — corrected in `72f5e8e`.
