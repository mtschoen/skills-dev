# Linter setup — skills-dev

Recommended linting setup for skills-dev — fleet survey 2026-05-29.

## Current state

**Languages detected**

| Language | Where | Count (approx) |
|---|---|---|
| Markdown | Skill definition files (`*/SKILL.md`, `*/references/*.md`, etc.) | ~71 files |
| Python | `tests/`, `cost-estimator/scripts/`, `pushback/evals/`, `fast-tests/evals/`, `remote-claude/references/` | ~10 canonical files; many more in `workspace/`/`evals/` scaffold (fixtures, generated runs) |
| Shell | `scripts/push-all.sh`, `scripts/pull-all.sh`, `install-skills.sh`, hook scripts in `wrap/`, `progress-beacon/` | ~10 canonical files; many copies in `escalate-over-shortcut/workspace/` (eval scaffold) |

No root-level `pyproject.toml` (individual eval scaffolds have their own). No `.editorconfig` at repo root. No `.pre-commit-config.yaml`. No Gitea Actions / GitHub Actions CI. No Claude Code `PostToolUse` hook in `.claude/settings.json` (file does not exist).

**Baseline finding count (ruff, canonical sources only)**

```
ruff check tests/ cost-estimator/scripts/ pushback/evals/ fast-tests/evals/ remote-claude/references/
Found 11 errors. [*] 2 fixable with --fix.
```

Breakdown: 1 `E741` (ambiguous variable name `l` in `remote-claude.py`), 2 `F401` (unused imports in `tests/test_scripts.py`), 8 `F811` (redefined fixture imports in test file). All fixable or trivially hand-fixed; nothing alarming.

---

## Proportionality note

This is a skills repo — mostly Markdown skill definitions, with supporting Python scripts and shell hooks. The linting value is:

1. **High** for the Python scripts (eval runners, pricing helpers, test suite) — real code, real bugs possible.
2. **High** for the shell scripts (`scripts/*.sh`, `install-skills.sh`, hook scripts) — shellcheck catches real portability issues.
3. **Low-to-optional** for the Markdown skill files — markdownlint adds value mainly for enforcing consistent header style; skip if it creates friction.

Do NOT apply ruff/shellcheck to the `workspace/` and `evals/workspace/` trees — those are generated eval fixtures and agent run outputs, not authored code. Exclude them explicitly (see configs below).

---

## Three-tier model

The three tiers are:

1. **On-save** — fast, per-file, Claude Code `PostToolUse` hook. Catches issues as code is written.
2. **Validate** — full-repo, all rules, authoritative. The go-to command and the lint dimension of `/maintaining-full-coverage`. Zero findings is the bar.
3. **CI** — automates tier 2 (+ tests) so regressions block at merge.

Tiers 1 and 2 use the same tool (`ruff` / `shellcheck`) in different modes.

### Recommendation table

| Tier | Python | Shell | Markdown |
|---|---|---|---|
| **① On-save** | `ruff format <file>` + `ruff check --fix <file>` | `shfmt -w <file>` | optional: `markdownlint-cli2 <file>` |
| **② Validate** | `ruff check <paths>` + `ruff format --check <paths>` | `shellcheck <scripts>` | `markdownlint-cli2 <paths>` (optional) |
| **③ CI** | `ruff check .` + `ruff format --check .` | `shellcheck scripts/*.sh install-skills.sh wrap/hooks/*.sh progress-beacon/hooks/*.sh` | same as ② (optional) |

**Why ruff:** replaces flake8 + black + isort + pyupgrade in one Rust binary; 10–100× faster. Already installed on this machine.

**Why shellcheck:** catches bash portability bugs, unquoted expansions, `[ ]` vs `[[ ]]` misuse. On this machine: `apt install shellcheck` / `brew install shellcheck` / `scoop install shellcheck`.

**Why markdownlint-cli2 is optional here:** skill files have their own conventions that don't always follow markdownlint defaults; lint rules would need tuning to avoid false positives on code fences and custom frontmatter patterns.

---

## Ruff config (add to a root `pyproject.toml`)

```toml
[tool.ruff]
# Exclude generated eval runs and workspace fixtures — not authored code.
exclude = [
    "*/workspace/**",
    "*/evals/scenarios/**/workspace/**",
    "smoke-test/evals/fixtures/node-api/node_modules/**",
]

[tool.ruff.lint]
select = ["F", "I", "B", "UP", "SIM", "RET", "PIE", "C4", "W", "RUF", "E741"]
# E501 (line too long) left out — markdown-embedded commands run long.
# E402 left out — scripts sometimes have late imports after __main__ guards.

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["RUF012", "RUF043", "SIM117", "B017", "SIM115"]
# Eval scaffold — generated, not enforced.
"**/evals/**" = ["F401", "F811", "E741"]
```

---

## On-save hook (Python)

Paste into `.claude/settings.json` under `hooks.PostToolUse`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "f=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty'); case \"$f\" in *.py) o=$(ruff check \"$f\" 2>/dev/null); [ -n \"$o\" ] && jq -n --arg c \"ruff:\\n$o\" '{hookSpecificOutput:{hookEventName:\"PostToolUse\",additionalContext:$c}}';; esac; exit 0"
          }
        ]
      }
    ]
  }
}
```

For shell files, extend the `case` to also run shellcheck (once installed):

```
*.sh) o=$(shellcheck "$f" 2>/dev/null); [ -n "$o" ] && jq -n --arg c "shellcheck:\n$o" '{...}';;
```

---

## CI step

No Gitea Actions workflow exists yet. When you add one (`.gitea/workflows/lint.yml`):

```yaml
name: lint
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install ruff
        run: pip install ruff

      - name: ruff check
        run: ruff check tests/ cost-estimator/scripts/ pushback/evals/ fast-tests/evals/ remote-claude/references/

      - name: ruff format check
        run: ruff format --check tests/ cost-estimator/scripts/ pushback/evals/ fast-tests/evals/ remote-claude/references/

      - name: Install shellcheck
        run: sudo apt-get install -y shellcheck

      - name: shellcheck
        run: shellcheck scripts/*.sh install-skills.sh wrap/hooks/*.sh progress-beacon/hooks/*.sh tests/test-install.sh
```

Scope the paths explicitly rather than `.` to avoid running on `workspace/` eval artifacts. Once a root `pyproject.toml` with the `exclude` list is in place, `ruff check .` is safe to use instead.

---

## Rollout

Adopt without a big-bang:

1. **Mechanical autofix sweep** — `ruff check --fix <paths>` + `ruff format <paths>`, commit as one PR. The 11 current findings include 2 auto-fixable; the rest are quick hand-fixes (unused import, ambiguous variable name, fixture import pattern).
2. **Hand-fix the real findings** — resolve the 9 non-auto-fixable ones (mostly the `F811` fixture-import pattern in `tests/test_scripts.py` and the `E741` in `remote-claude.py`).
3. **Bake the gate** — add the on-save hook + CI workflow; zero findings becomes the bar.

**projdash reference:** projdash ran this same 3-step flow in PRs #113 (autofix sweep), #115 (real fixes), #116 (bake the gate). The decision to auto-fix + PR vs manually review first is yours.

The `workspace/` and `evals/workspace/` trees should be excluded permanently (see ruff config above) — they contain hundreds of agent-generated Python and shell files that aren't maintained to any linting standard and would flood the findings list.

---

## AI-slop gate (aislop)

**aislop** (https://github.com/scanaislop/aislop · MIT CLI · Node >= 20) is a
language-agnostic AI-slop quality gate — deterministic (no LLM), 40+ rules,
scored 0–100 — that flags agent slop: narrative/trivial comments, swallowed
exceptions, dead code, unused/hallucinated imports, `as any`, innerHTML sinks,
etc. It complements (does not replace) the per-language linters above and is
intended to run **per-edit + PR-gated across all repos with supported languages**.

**Applicability:** APPLIES — this repo has Python (`tests/`, `cost-estimator/scripts/`,
`pushback/evals/`, etc.). Shell and Markdown are outside aislop's scope; aislop
only scores the Python surface.

### Per-edit (① on-save)

```
aislop hook install --claude --project
```

Pin the binary version when prompted — never use `@latest` in a hook; it performs a
network version check on every edit.

### PR / CI gate (③)

```yaml
      - name: aislop
        run: npx --yes aislop@0.9.4 ci .
```

On Gitea Actions use the CLI (`npx --yes aislop@<ver> ci .`), NOT the GitHub
composite action `scanaislop/aislop@vX` (GitHub-only). **Pin a version (e.g.
0.9.4), not `@latest`.**

aislop scores the **whole repo** — there is no diff/changed-files mode. The CI
gate is "don't regress the whole-repo score", not a per-diff check.

### Config (`.aislop/config.yml`)

```yaml
ci:
  failBelow: 80   # reference: git-wizard gates at 80

exclude:
  - "*/workspace/**"
  - "*/evals/scenarios/**/workspace/**"
  - "smoke-test/evals/fixtures/**"
```

The generated `workspace/` and `evals/workspace/` trees must be in `exclude` —
same scope as the ruff exclude above — so they don't dominate the score with
hundreds of agent-generated files. `.aislop/config.yml` also accepts whole-engine
toggles (`format`, `lint`, `code-quality`, `ai-slop`, `security`, `architecture`)
but no per-rule config in version 0.9.4.

### Python-specific false positives (aislop 0.9.4)

- **`ai-slop/unused-import` on `from __future__ import annotations`** — aislop
  flags this as an unused import; ruff/pyflakes specifically exempt `__future__`
  imports. **Do NOT remove it** — removing the line changes annotation-evaluation
  semantics (PEP 563). This single false positive can dominate the score on a
  Python repo that uses this idiom widely.
- **`python-mutable-default` on FastAPI `Body(default={})`** — a valid FastAPI
  pattern; not slop.
- **No per-rule config in 0.9.4** — you can toggle whole engines but cannot silence
  individual rules. If the `__future__` false positive dominates your score (e.g.
  score drops below 80 purely from `from __future__ import annotations` files with
  nothing else wrong), exclude those files or defer gating until per-rule config
  lands in a later version.

### Rollout

Clean up first, then gate — don't ratchet from a noisy baseline. Run
`npx aislop@0.9.4 scan . -d` to assess the current score, exclude the generated
`workspace/` trees first (they will dominate otherwise), then address real findings
before setting `failBelow`. Reference: git-wizard uses `failBelow: 80`.

Full detail: `C:\Users\mtsch\.claude\notes\idioms_linters.md` (AI-slop gate section).
