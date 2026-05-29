# skills-dev — Claude Code instructions

This repo is the umbrella that ties together each skill's own submodule. Every top-level directory other than `.claude/`, `docs/`, `scripts/`, `LICENSE`, and `install-skills.*` is a git submodule pointing at that skill's own repository, mirrored on Gitea (primary) and GitHub (public).

## Adding a new skill

**Every new skill needs its own repo.** Don't add a new top-level directory directly to skills-dev — convert it to a submodule.

The workflow:

1. Author the skill content locally in a temporary `<name>/` directory inside skills-dev.
2. Create the remote repos:
   - Gitea: `schoen/skills-<name>` (private). Owned by `schoen`, so use `~/.gitea-token` (admin) — `~/.gitea-token-claude` can't create under another user's namespace.
   - GitHub: `mtschoen/skills-<name>` (public). Use `gh repo create`.
3. Init the local dir as git, commit, push to Gitea. (Use the default Matt Schoen git identity — the global CLAUDE.md's bot-identity pattern is only for PRs where Gitea's self-approval block matters, not for direct main-branch commits.)
4. Remove the local dir. **Windows gotcha:** `cd ..` first to avoid `Device or resource busy` on the cwd.
5. Add as submodule. **Sequencing pitfall:** `git submodule add ../skills-<name>.git <name>` resolves the relative URL against whichever superproject remote git picks first (alphabetically `github` before `origin`). At this step GitHub is still empty (only Gitea has the initial commit from step 3), so the relative-URL form fails with `cloned an empty repository / branch yet to be born / unable to checkout submodule`. Use the **absolute Gitea URL**, then rewrite `.gitmodules` to the relative form:

   ```bash
   git submodule add gitea@llamabox.internal:schoen/skills-<name>.git <name>
   git config -f .gitmodules submodule.<name>.url ../skills-<name>.git
   ```

   Do **not** run `git submodule sync` after the rewrite — it can propagate the relative URL into the submodule's working-tree `origin` and break daily git ops. The working-tree origin should remain the SSH Gitea URL set by `submodule add`.
6. Configure per-submodule remotes: `origin` → Gitea (SSH, already set by step 5), `github` → GitHub (SSH, `git@github.com:mtschoen/skills-<name>.git`). Push to GitHub: `git -C <name> push github main` — **no `-u`**, since main's upstream should stay at `origin/main` (set by step 5). Using `-u github` here silently retargets the upstream and breaks the convention.
7. Confirm `install-skills.{sh,bat}` picks up the new skill via dry run: `./install-skills.sh -n <name>`. (For fresh installs the dry-run output is just one line: `install <name> -> ~/.claude/skills/<name>`. That's normal — file-listing diffs only appear for already-installed skills.)
8. Commit the submodule pointer in skills-dev.
9. Run `scripts/push-all.{sh,bat}` to push both hosts.

The detailed concrete steps (with current Gitea endpoints and Windows gotchas) live at `~/.claude/projects/C--Users-mtsch-skills-dev/memory/reference_gitea_submodule_workflow.md`. Read that for the API tokens and curl commands; the user's global CLAUDE.md (`Gitea (self-hosted)` section) is authoritative for current state since the memory note may predate URL/token changes.

## Naming conventions

- Repo names use the `skills-<name>` prefix on **both** hosts. The skills-dev submodule path is the bare `<name>` (no prefix).
- `.gitmodules` uses **relative URLs** (`../skills-<name>.git`) so the same `.gitmodules` resolves correctly whether the index was cloned from Gitea or GitHub. (Established via the rewrite in step 5 above.)
- Per-submodule remote convention: `origin` → Gitea (SSH), `github` → GitHub (SSH).
- Don't run `git submodule sync` after manually fixing a submodule's `origin` URL — it can overwrite working-tree URLs from `.gitmodules` resolution. The submodule directories in skills-dev have full `.git/` dirs (not gitfiles), so daily git ops read from `<sub>/.git/config`, not `.git/modules/<sub>/config`.
- A skill ships extra top-level content (beyond `SKILL.md` + `scripts/` + `references/` + `assets/`) by listing it in a `.skillpack` file at the skill's repo root. Current users: `progress-beacon` (`hooks/`), `cost-estimator` (`REPORT_TEMPLATE.md`). The `.skillpack` file is itself never installed.

## Layout

Per-skill repos use the **root layout**: `SKILL.md` at the repo root, plus `evals/`, `README.md`, and `workspace/` (gitignored). The installer (`install-skills.{sh,bat}`) ships only **git-tracked** files (`git ls-files`), filtered to a **top-level allowlist**: `SKILL.md` + `scripts/` + `references/` + `assets/`, plus any extra top-level entries a skill declares in an optional `.skillpack` manifest at its repo root (one entry per line, `#` comments). Shipping tracked-only means generated junk (`__pycache__`, `.pytest_cache`) can never leak; the allowlist means dev dirs (`evals/`, `tests/`, `workspace/`, `README.md`, `LICENSE`) are excluded by omission. Each install mirrors a clean staging tree into the destination, so files left by older installs are removed. Skill validation is delegated to the official Agent Skills validator: CI runs `agentskills validate` (pinned `skills-ref==0.1.1`) over every `.gitmodules` skill via `scripts/validate_skills.py`, which keeps the fleet-level anti-vacuous / WIP-skip guards; markdownlint covers skill prose.

## Working across all submodules

- `scripts/push-all.{sh,bat}` — push every active submodule plus the umbrella to both `origin` (Gitea) and `github` (GitHub). Each push is pre-flighted: fetch the remote and classify local main vs remote/main as up-to-date / FF / behind / diverged. Non-FF states are reported with a clear reason ("behind by N", "DIVERGED: ahead N, behind M") and the push is skipped instead of failing with a generic line. Errors don't halt the run, but the script exits non-zero with a summary of all issues at the end.
- `scripts/pull-all.{sh,bat}` — pull latest from Gitea on every submodule plus the umbrella.

**Fresh-clone setup:** run `git config submodule.recurse true` once per clone (it can't be committed — `.git/config` is per-clone). Without it, pulling the umbrella advances the recorded submodule pointers but leaves local checkouts behind, producing the recurring `M <submodule> (new commits)` drift. See README "Cloning" for the trade-off (pulls then detach submodule HEADs; pull-all re-attaches to main).

## Specs and plans

In-flight design specs live in `docs/superpowers/specs/` and implementation plans in `docs/superpowers/plans/`. Both are scaffolding — distilled into the plan header on spec→plan handoff, then deleted at branch-finish. Lasting design rationale folds into per-skill `SKILL.md` and `README.md` files.
