# skills-dev - agent instructions

This repo is the umbrella that ties together three themed family submodules, each an independently adoptable set of related skills. Every top-level directory other than `.claude/`, `.github/`, `ci/`, `docs/`, `hooks/`, `scripts/`, `tests/`, `LICENSE`, `pyproject.toml`, `uv.lock`, and `install-skills.*` is a git submodule pointing at a family repository on GitHub: `completion-discipline`, `orchestration`, and `working-method`.

## Adding a new skill

**A new skill is a directory inside the right family submodule, not a new repo.** Don't add a new top-level directory directly to skills-dev - it goes one level down, inside an existing family.

The workflow:

1. Pick the family (see "Choosing a family" below).
2. `mkdir <family>/<skill-name>` and author `SKILL.md` (plus `scripts/`, `references/`, `assets/`, `evals/` as needed) directly in the family submodule's working tree.
3. Commit and push inside the family submodule: `git -C <family> add <skill-name> && git -C <family> commit -m "..." && git -C <family> push`.
4. Confirm `install-skills.{sh,bat}` picks up the new skill via dry run: `./install-skills.sh -n <skill-name>`. (For fresh installs the dry-run output is just one line: `install <skill-name> -> ~/.claude/skills/<skill-name>`. That's normal - file-listing diffs only appear for already-installed skills.)
5. Commit the advanced submodule pointer in skills-dev.
6. Run `scripts/push-all.{sh,bat}`.

### Choosing a family

The three families are thesis-bound, not just topic buckets - each family's own `README.md` states its argument in full. As a quick router:

- **`completion-discipline`** - the skill fires at a point an agent might declare something done (a change, a session, a handover) and forces a check before that claim stands.
- **`working-method`** - the skill changes how an agent arrives at an answer while the work is still in progress: what it trusts, what it verifies, what habit it substitutes for a cheaper reflex.
- **`orchestration`** - the skill is about the seam between agents, machines, or budgets: more than one agent, more than one host, or a quota/cost concern.

Boundaries between the three are intentionally fuzzy at the edges; a skill sitting slightly awkwardly in a family is cheaper than inventing a fourth family for it.

### Why families, not one repository per skill or a single flat repo

Each skill repository carries its own CI workflow, branch protection policy, markdownlint config, and pair of forge remotes. That configuration and maintenance tax scales linearly with every skill added and buys nothing back in practice: a change that touches several repositories costs a PR per repository plus a pointer bump, so cross-cutting changes get done ad hoc or skipped. Three family submodules cut that surface to a handful of endpoints and workflows while keeping `mkdir <family>/<skill-name>` as the entire cost of adding a skill.

A single flat repository would cut the surface further still, but skills are published into a saturated ecosystem where an undifferentiated pile of skills reads as a kitchen sink and gets skipped. A themed family with a real README argument for why its skills belong together reads as a coherent, independently adoptable set - someone who wants the orchestration set can take it without the completion-discipline set. That independent adoptability, not repository count by itself, is what a flat monorepo cannot offer.

### A skill that belongs with its tool, not here

A skill whose value collapses without a specific tool - it registers with a database that has no working by-hand fallback, or it enumerates a set with no defined source once the tool is absent - does not belong in this public set. It ships next to the tool instead, as `packages/<package>/skills/<skill-name>/` or `satellites/<satellite>/skills/<skill-name>/` inside the `schoen-lab` monorepo, following the precedent of `capture-idea`/`find-task`/`promote-project` (`packages/project_tracker/skills/`), `check-memory`/`memory-cleanup` (`packages/replica/skills/`), and `progress-beacon` (`satellites/agent-statusline/skills/`, alongside the `statusline` skill it complements). The test is whether the skill documents a by-hand path that still delivers its value, not whether it calls the tool or how often. Those skills are installed by the owning package's or satellite's own tooling (`onboard`'s `SkillsFeature` copies `statusline` directly, for example) rather than by this repo's `install-skills.sh`; `scripts/validate_skills.py` and `scripts/check_config_drift.py` can additionally validate them via an `--extra-skill-root <path>` flag, scanning `packages/*/skills/*` and `satellites/*/skills/*` under the given root, without them needing to be submodules here.

## Naming conventions

- Repo names use the `skills-<family-name>` prefix. The skills-dev submodule path is the bare `<family-name>` (no prefix). A skill's own directory name inside a family carries no prefix either.
- `.gitmodules` uses **relative URLs** (`../skills-<family-name>.git`), which resolve against whichever remote the umbrella was cloned from.
- Each family submodule's `origin` is its own GitHub repo over SSH (`git@github.com:mtschoen/skills-<family-name>.git`). `git submodule add` does NOT guarantee this: it sets the working-tree `origin` from the resolved relative URL, i.e. whatever forge the umbrella clone's `origin` points at (Gitea on chonkers). After adding a family submodule, reset it - `git -C <family-name> remote set-url origin git@github.com:mtschoen/skills-<family-name>.git` - and add a `gitea` remote for the Gitea sibling. Don't run `git submodule sync` after manually fixing a submodule's `origin` URL - it can overwrite working-tree URLs from `.gitmodules` resolution.
- The submodule directories in skills-dev are **gitfiles**: `<sub>/.git` is a file reading `gitdir: ../../.git/modules/<sub>`, so config and refs live under `.git/modules/<sub>/`, not in the submodule directory. Two consequences worth knowing: `git rev-parse --git-common-dir` from a submodule points **outside** its own checkout, and `git worktree list --porcelain` reports that git directory rather than the working tree - so neither can be used to derive a submodule's checkout root. Walk up the filesystem for the nearest `.git` entry instead.
- A skill ships extra top-level content (beyond `SKILL.md` + `scripts/` + `references/` + `assets/`) by listing it in a `.skillpack` file at the skill's own root. Current users: `cost-estimator` (`REPORT_TEMPLATE.md`), `project-lock` (`hooks/`), `research-first` (`hooks/`), `wrap` (`hooks/`). The `.skillpack` file is itself never installed.

## Layout

Each skill uses the **root layout**: `SKILL.md` at the skill's own root, plus `evals/`, `README.md`, and `workspace/` (gitignored), whether that skill sits two levels down under a family submodule here or as a plain subdirectory under `packages/*/skills/*` or `satellites/*/skills/*` elsewhere. The installer (`install-skills.{sh,bat}`) ships only **git-tracked** files (`git ls-files`), filtered to a **top-level allowlist**: `SKILL.md` + `scripts/` + `references/` + `assets/`, plus any extra top-level entries a skill declares in an optional `.skillpack` manifest at its own root (one entry per line, `#` comments). Shipping tracked-only means generated junk (`__pycache__`, `.pytest_cache`) can never leak; the allowlist means dev dirs (`evals/`, `tests/`, `workspace/`, `README.md`, `LICENSE`) are excluded by omission. Each install mirrors a clean staging tree into the destination, so files left by older installs are removed. Skill validation is delegated to the official Agent Skills validator: CI runs `agentskills validate` (pinned `skills-ref==0.1.1`) over every skill via `scripts/validate_skills.py`, which discovers skills up to one level under each `.gitmodules`-declared family submodule and keeps the fleet-level anti-vacuous / WIP-skip guards plus a portability guard (no tracked file in the umbrella or any skill - dev files included - may reference local-only paths such as user memory notes or machine-specific home dirs; deny patterns and exemptions live in `validate_skills.py`); markdownlint covers skill prose.

**Mid-session skill staleness is partial.** The skills *listing* (names and descriptions) is fixed at session start, so frontmatter changes need a new session. The skill *body* is not: an explicit `Skill` tool invocation reads the installed `SKILL.md` at call time, so an edit-install-invoke loop within one session is a valid way to test body changes - verified 2026-08-05, when a wrap invocation returned text edited minutes earlier. A contrary observation on 2026-08-04 (reinstalled wrap, invoked it, got the pre-change version) was real but has not reproduced, so verify with `grep` against the installed file rather than assuming either behaviour. Related trap with the same symptom and no error: auditing a skill you forgot to install at all.

Note also that `install-skills.sh` prompts before overwriting and needs a tty; from an agent shell it prints `/dev/tty: No such device or address` and **silently skips every target**. Pass `-y`.

## Linting

The umbrella has a lint gate over **umbrella-owned code only** - `scripts/`, `tests/`, and `ci/` Python, plus the umbrella shell scripts. Each skill is its own submodule/repo and owns its own gate, so submodule trees are excluded (`pyproject.toml` `[tool.ruff] exclude`). The bar is **0 findings**; `TEST-REPORT.md` at the repo root records the current state. The validate-tier (authoritative) commands:

```bash
ruff check scripts/ tests/ ci/
ruff format --check scripts/ tests/ ci/
shellcheck scripts/*.sh install-skills.sh tests/test-install.sh
aislop ci  # AI-slop/code-quality/security + format, score-100 gate (fork binary; see "Quality gate: aislop")
```

CI runs these as the `ruff`, `shellcheck`, and `aislop` jobs in `.github/workflows/lint.yml`. An on-save `PostToolUse` hook (`.claude/hooks/ruff_on_save.py` for ruff/shellcheck, plus `aislop hook claude`, both wired in the tracked `.claude/settings.json`) lints files as they're edited - advisory, never blocking - and because sessions usually run from the umbrella, it covers submodule files too when you touch them. The ruff branch also auto-applies `ruff format` on each `.py` edit so a save never leaves format drift behind. shellcheck is optional locally (CI installs it); install `shellcheck-py` via pip to run it on Windows. Ruff config lives in `pyproject.toml`; when adding a new submodule, add its dir to the `exclude` list there.

There is also a committed git hook at `hooks/pre-commit` that is the authoritative, author/machine-independent backstop: it re-runs CI's hard ruff gates (`ruff format --check` + `ruff check` on `scripts/ tests/ ci/`) and blocks the commit on any finding, so ruff format/lint drift can never reach CI. It deliberately does NOT run shellcheck, which is not guaranteed to be installed locally (CI installs it; on Windows it needs `shellcheck-py` via pip), so gating every commit on it would block clones that never opted in; shellcheck stays CI-only. `.gitattributes` pins `*.sh` to `text eol=lf`, so a Windows checkout no longer materializes them with CRLF and the SC1017 "literal carriage return" false positive that used to bury shellcheck output on Windows is gone. `core.hooksPath` is per-clone local config (not committed), so enable it once per clone with `git config core.hooksPath hooks` (verify with `git config core.hooksPath`).

**aislop** ([scanaislop/aislop](https://github.com/scanaislop/aislop)) is a project-scoped quality gate (`.aislop/config.yml`, `ci.failBelow: 100`, umbrella-scoped via submodule excludes, telemetry off). It's wired **manually and pinned** - do **not** run `aislop hook install` (its default is a *global* install that rewrites `~/.claude/settings.json` and appends to your global `CLAUDE.md`; even `--project` writes an `AISLOP.md` + CLAUDE.md import). aislop's format engine is enabled as a redundant belt-and-suspenders check, and `python-linting` (ruff check passthrough) stays off - the dedicated `ruff` job/hook owns Python format+lint, aislop owns AI-slop, code-quality, and security. The fork prefers the project's PATH ruff over its vendored copy, so the aislop CI job installs the pinned `ruff==0.15.15` to keep aislop's format pass identical to the dedicated ruff gate.

## Working across all submodules

- `scripts/push-all.{sh,bat}` - push every active submodule plus the umbrella to `origin`, skipping repos that lack it; `--remote <name>` adds another remote where it exists. Each push is pre-flighted: fetch the remote and classify local main vs remote/main as up-to-date / FF / behind / diverged. Non-FF states are reported with a clear reason ("behind by N", "DIVERGED: ahead N, behind M") and the push is skipped instead of failing with a generic line. Errors don't halt the run, but the script exits non-zero with a summary of all issues at the end.
- `scripts/pull-all.{sh,bat}` - pull latest from `origin` on every submodule plus the umbrella.
- `scripts/clean-room.sh` - sourceable library for skill audit harnesses. Builds a headless session containing the skill under test and as little of the operator's machine as possible: `--setting-sources project` (drops user settings, hence their hooks and every user-installed skill), `--strict-mcp-config`, and `--plugin-dir` at the skill's own checkout (a directory with `SKILL.md` at its root and no `skills/` subdir loads as a single-skill plugin, Claude Code >= 2.1.142). It also owns the traps, each of which silently produces a fake result rather than an error: fixtures must live **outside `$HOME`** (memory discovery walks cwd upward, and `%TEMP%` is under home on Windows), `CLAUDE_CONFIG_DIR` must be a **host-native** path (a POSIX path makes claude.exe fall back to an empty config and every turn dies `Not logged in`), and the invocation token is `/<plugin-dir-basename>:<frontmatter-name>` - a bare `/name` resolves to nothing and the session improvises a plausible answer from the description. Consumer: `wrap/tests/run-audit.sh` (`-c` clean room, `-C` control). Skill harnesses that source it are umbrella-only, which is fine - `tests/` is dev-only and never shipped by the installer.

**Fresh-clone setup:** run `git config submodule.recurse true` once per clone (it can't be committed - `.git/config` is per-clone). Without it, pulling the umbrella advances the recorded submodule pointers but leaves local checkouts behind, producing the recurring `M <submodule> (new commits)` drift. See README "Cloning" for the trade-off (pulls then detach submodule HEADs; pull-all re-attaches to main).

## Specs and plans

In-flight design specs live in `docs/superpowers/specs/` and implementation plans in `docs/superpowers/plans/`. Both are scaffolding - distilled into the plan header on spec-to-plan handoff, then deleted at branch-finish. Lasting design rationale folds into per-skill `SKILL.md` and `README.md` files.

## Quality gate: aislop

This project uses **aislop** as a deterministic quality gate for AI-written code
(narrative comments, swallowed exceptions, `as any`, dead stubs, oversized
functions, etc.) across TS/JS, Python, Go, Rust, Ruby, PHP, Java, and C#.

`aislop` is installed globally on this machine (pinned to the fork
`mtschoen/aislop`, which adds C#/roslynator support). Call the installed binary
directly - do NOT use `npx aislop`, which pulls upstream from npm with no C#
support:

- **Before declaring work complete**, run `aislop scan .` and address findings.
- **Before committing**, run `aislop scan --staged` (staged files only).
- `aislop fix` auto-clears mechanical issues (formatting, unused imports, dead
  code); `aislop fix --claude` hands the rest back with full context.
- `aislop ci .` is the gate - exits non-zero if the score drops below the
  threshold in `.aislop/config.yml`. Treat a failing gate like a failing test.

To refresh the pinned binary after new commits land on the fork branch:
`pnpm add -g --allow-build=aislop "github:mtschoen/aislop#schoen/main"`

## Dependency policy

Skills reference each other and external tools at three levels:

- **Hard dependency** - the skill is meaningless without it (e.g. fleet-orchestration requires superpowers:dispatching-parallel-agents; memory-cleanup requires the replica CLI). Declare it explicitly: name it in the frontmatter description ("Requires ...") and give an install pointer or link in a Requirements section. No fallback text needed.
- **Soft dependency** - the skill works alone but is enhanced by another skill or MCP server. Reference it conditionally ("if X is installed ...") and state the standalone fallback where one is cheap to describe. Do not contort the text just for isolation's sake.
- **Suite** - a declared group designed to be installed together. Members may reference each other plainly; each member's README notes the suite membership once. Current suites: the completion suite = the full `completion-discipline` family (`maintaining-full-coverage`, `smoke-test`, `docs-update`, `escalate-over-shortcut`, `wrap`, `reconcile-tasks`, `project-maintenance`).

External tools get a link on first mention in each skill: project-tracker (part of <https://github.com/mtschoen/schoen-lab>), git-wizard (<https://github.com/mtschoen/git-wizard>), aislop (<https://github.com/scanaislop/aislop/>), replica (part of <https://github.com/mtschoen/schoen-lab>), agent-walker (<https://github.com/mtschoen/agent-walker>), pi (<https://pi.dev/>).

## Superpowers fork

These skills are designed against the superpowers fork at <https://github.com/mtschoen/superpowers>, which changes upstream's rules around parallel subagent dispatch and plan/spec file handling. Notably, official superpowers 6.2.0 forbids dispatching implementation subagents in parallel; the fork's subagent-driven-development adds Parallel Dispatch (Worktree Isolation). Skills that describe parallel SDD (review-in-parallel-pipelines, fleet-orchestration) assume the fork.
