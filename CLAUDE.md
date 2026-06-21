# skills-dev — Claude Code instructions

This repo is the umbrella that ties together each skill's own submodule. Every top-level directory other than `.claude/`, `docs/`, `scripts/`, `LICENSE`, and `install-skills.*` is a git submodule pointing at that skill's own repository, mirrored on Gitea (primary) and GitHub (public).

## Adding a new skill

**Every new skill needs its own repo.** Don't add a new top-level directory directly to skills-dev — convert it to a submodule.

The workflow:

1. Author the skill content locally in a temporary `<name>/` directory inside skills-dev.
2. Create the remote repos:
   - Gitea: `schoen/skills-<name>` (**public** — umbrella CI's `submodules: recursive` checkout clones sibling repos anonymously, so a private repo breaks the `markdown` and `validate-skills` jobs; the run token only covers skills-dev itself). Owned by `schoen`, so use `~/.gitea-token` (admin) — `~/.gitea-token-claude` can't create under another user's namespace. Also enable the Actions unit if the repo gets CI (`PATCH {"has_actions": true}` — disabled by default on API-created repos).
   - GitHub: `mtschoen/skills-<name>` (public). Use `gh repo create`.
3. Init the local dir as git, commit, push to Gitea. (Use the default Matt Schoen git identity — the global CLAUDE.md's bot-identity pattern is only for PRs where Gitea's self-approval block matters, not for direct main-branch commits.)
4. Remove the local dir. **Windows gotcha:** `cd ..` first to avoid `Device or resource busy` on the cwd.
5. Add as submodule. **Sequencing pitfall:** `git submodule add ../skills-<name>.git <name>` resolves the relative URL against whichever superproject remote git picks first (alphabetically `github` before `origin`). At this step GitHub is still empty (only Gitea has the initial commit from step 3), so the relative-URL form fails with `cloned an empty repository / branch yet to be born / unable to checkout submodule`. Use the **absolute Gitea URL**, then rewrite `.gitmodules` to the relative form:

   ```bash
   git submodule add gitea@llamabox.sticktoitive.net:schoen/skills-<name>.git <name>
   git config -f .gitmodules submodule.<name>.url ../skills-<name>.git
   ```

   Do **not** run `git submodule sync` after the rewrite — it can propagate the relative URL into the submodule's working-tree `origin` and break daily git ops. The working-tree origin should remain the SSH Gitea URL set by `submodule add`.
6. Configure per-submodule remotes: `origin` → Gitea (SSH, already set by step 5), `github` → GitHub (SSH, `git@github.com:mtschoen/skills-<name>.git`). Push to GitHub: `git -C <name> push github main` — **no `-u`**, since main's upstream should stay at `origin/main` (set by step 5). Using `-u github` here silently retargets the upstream and breaks the convention.
7. Confirm `install-skills.{sh,bat}` picks up the new skill via dry run: `./install-skills.sh -n <name>`. (For fresh installs the dry-run output is just one line: `install <name> -> ~/.claude/skills/<name>`. That's normal — file-listing diffs only appear for already-installed skills.)
8. Commit the submodule pointer in skills-dev.
9. Run `scripts/push-all.{sh,bat}` to push both hosts.

The detailed concrete steps (current Gitea endpoints, API tokens, curl commands, Windows gotchas) live in the auto-loaded project memory - see the "gitea submodule workflow" entry in its MEMORY.md index. The user's global CLAUDE.md (`Gitea (self-hosted)` section) is authoritative for current state since the memory note may predate URL/token changes.

## Naming conventions

- Repo names use the `skills-<name>` prefix on **both** hosts. The skills-dev submodule path is the bare `<name>` (no prefix).
- `.gitmodules` uses **relative URLs** (`../skills-<name>.git`) so the same `.gitmodules` resolves correctly whether the index was cloned from Gitea or GitHub. (Established via the rewrite in step 5 above.)
- Per-submodule remote convention: `origin` → Gitea (SSH), `github` → GitHub (SSH).
- Don't run `git submodule sync` after manually fixing a submodule's `origin` URL — it can overwrite working-tree URLs from `.gitmodules` resolution. The submodule directories in skills-dev have full `.git/` dirs (not gitfiles), so daily git ops read from `<sub>/.git/config`, not `.git/modules/<sub>/config`.
- A skill ships extra top-level content (beyond `SKILL.md` + `scripts/` + `references/` + `assets/`) by listing it in a `.skillpack` file at the skill's repo root. Current users: `progress-beacon` (`hooks/`), `cost-estimator` (`REPORT_TEMPLATE.md`). The `.skillpack` file is itself never installed.

## Layout

Per-skill repos use the **root layout**: `SKILL.md` at the repo root, plus `evals/`, `README.md`, and `workspace/` (gitignored). The installer (`install-skills.{sh,bat}`) ships only **git-tracked** files (`git ls-files`), filtered to a **top-level allowlist**: `SKILL.md` + `scripts/` + `references/` + `assets/`, plus any extra top-level entries a skill declares in an optional `.skillpack` manifest at its repo root (one entry per line, `#` comments). Shipping tracked-only means generated junk (`__pycache__`, `.pytest_cache`) can never leak; the allowlist means dev dirs (`evals/`, `tests/`, `workspace/`, `README.md`, `LICENSE`) are excluded by omission. Each install mirrors a clean staging tree into the destination, so files left by older installs are removed. Skill validation is delegated to the official Agent Skills validator: CI runs `agentskills validate` (pinned `skills-ref==0.1.1`) over every `.gitmodules` skill via `scripts/validate_skills.py`, which keeps the fleet-level anti-vacuous / WIP-skip guards plus a portability guard (no tracked file in the umbrella or any skill - dev files included - may reference local-only paths such as user memory notes or machine-specific home dirs; deny patterns and exemptions live in `validate_skills.py`); markdownlint covers skill prose.

## Linting

The umbrella has a lint gate over **umbrella-owned code only** — `scripts/` and `tests/` Python, plus the umbrella shell scripts. Each skill is its own submodule/repo and owns its own gate, so submodule trees are excluded (`pyproject.toml` `[tool.ruff] exclude`). The bar is **0 findings**; `TEST-REPORT.md` at the repo root records the current state. The validate-tier (authoritative) commands:

```bash
ruff check scripts/ tests/
ruff format --check scripts/ tests/
shellcheck scripts/*.sh install-skills.sh tests/test-install.sh
npx -y @schoen/aislop@0.12.3 ci # AI-slop/code-quality/security + format, score-100 gate
```

CI runs these as the `ruff`, `shellcheck`, and `aislop` jobs in `.gitea/workflows/lint.yml`. An on-save `PostToolUse` hook (`.claude/hooks/ruff_on_save.py` for ruff/shellcheck, plus `aislop hook claude`, both wired in the tracked `.claude/settings.json`) lints files as they're edited — advisory, never blocking — and because sessions usually run from the umbrella, it covers submodule files too when you touch them. The ruff branch also auto-applies `ruff format` on each `.py` edit so a save never leaves format drift behind. shellcheck is optional locally (CI installs it); install `shellcheck-py` via pip to run it on Windows. Ruff config lives in `pyproject.toml`; when adding a new submodule, add its dir to the `exclude` list there.

There is also a committed git hook at `hooks/pre-commit` that is the authoritative, author/machine-independent backstop: it re-runs CI's hard ruff gates (`ruff format --check` + `ruff check` on `scripts/ tests/`) and blocks the commit on any finding, so ruff format/lint drift can never reach CI. It deliberately does NOT run shellcheck: on Windows the `.sh` files are checked out CRLF, which shellcheck flags as SC1017 (a false positive that would block every commit); shellcheck stays CI-only (Linux, LF). `core.hooksPath` is per-clone local config (not committed), so enable it once per clone with `git config core.hooksPath hooks` (verify with `git config core.hooksPath`).

**aislop** ([scanaislop/aislop](https://github.com/scanaislop/aislop)) is a project-scoped quality gate (`.aislop/config.yml`, `ci.failBelow: 100`, umbrella-scoped via submodule excludes, telemetry off). It's wired **manually and pinned** — do **not** run `aislop hook install` (its default is a *global* install that rewrites `~/.claude/settings.json` and appends to your global `CLAUDE.md`; even `--project` writes an `AISLOP.md` + CLAUDE.md import). aislop's format engine is enabled as a redundant belt-and-suspenders check, and `python-linting` (ruff check passthrough) stays off — the dedicated `ruff` job/hook owns Python format+lint, aislop owns AI-slop, code-quality, and security. Format was *off* until `@schoen/aislop@0.12.2`, which makes aislop prefer the project's PATH ruff over its vendored copy ([mtschoen/aislop#1](https://github.com/mtschoen/aislop/pull/1)); before that the vendored ruff could disagree with ours on shebang/docstring spacing, so the aislop CI job now installs the pinned `ruff==0.15.15` to keep aislop's format pass identical to the dedicated ruff gate. Pin the fork version everywhere (`@schoen/aislop@0.12.3`); it's pre-1.0.

## Working across all submodules

- `scripts/push-all.{sh,bat}` — push every active submodule plus the umbrella to both `origin` (Gitea) and `github` (GitHub). Each push is pre-flighted: fetch the remote and classify local main vs remote/main as up-to-date / FF / behind / diverged. Non-FF states are reported with a clear reason ("behind by N", "DIVERGED: ahead N, behind M") and the push is skipped instead of failing with a generic line. Errors don't halt the run, but the script exits non-zero with a summary of all issues at the end.
- `scripts/pull-all.{sh,bat}` — pull latest from Gitea on every submodule plus the umbrella.

**Fresh-clone setup:** run `git config submodule.recurse true` once per clone (it can't be committed — `.git/config` is per-clone). Without it, pulling the umbrella advances the recorded submodule pointers but leaves local checkouts behind, producing the recurring `M <submodule> (new commits)` drift. See README "Cloning" for the trade-off (pulls then detach submodule HEADs; pull-all re-attaches to main).

## Specs and plans

In-flight design specs live in `docs/superpowers/specs/` and implementation plans in `docs/superpowers/plans/`. Both are scaffolding — distilled into the plan header on spec→plan handoff, then deleted at branch-finish. Lasting design rationale folds into per-skill `SKILL.md` and `README.md` files.

## Quality gate: aislop

This project uses **aislop** as a deterministic quality gate for AI-written code
(narrative comments, swallowed exceptions, `as any`, dead stubs, oversized
functions, etc.) across TS/JS, Python, Go, Rust, Ruby, PHP, Java, and C#.

`aislop` is installed globally on this machine (pinned to the fork
`mtschoen/aislop`, which adds C#/roslynator support). Call the installed binary
directly — do NOT use `npx aislop`, which pulls upstream from npm with no C#
support:

- **Before declaring work complete**, run `aislop scan .` and address findings.
- **Before committing**, run `aislop scan --staged` (staged files only).
- `aislop fix` auto-clears mechanical issues (formatting, unused imports, dead
  code); `aislop fix --claude` hands the rest back with full context.
- `aislop ci .` is the gate — exits non-zero if the score drops below the
  threshold in `.aislop/config.yml`. Treat a failing gate like a failing test.

To refresh the pinned binary after new commits land on the fork branch:
`pnpm add -g --allow-build=aislop "github:mtschoen/aislop#feat/csharp-support"`
