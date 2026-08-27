# skills-dev

A workspace for developing agent skills - reusable capabilities for AI coding assistants including Codex, opencode, [Claude Code](https://claude.com/claude-code), Antigravity, and Hermes. Each top-level directory is a git submodule pointing at a family repository - a themed, independently adoptable set of related skills living as plain subdirectories - and this repo is the umbrella that ties the families together and provides install + sync tooling.

## What's here

Three family submodules, each with its own thesis for why its skills belong together (see each family's own `README.md` for the full argument):

**`completion-discipline`** (7 skills) - what an agent owes the work at the point it stops: `maintaining-full-coverage` (hold the coverage/lint bar, never lower it silently), `smoke-test`, `docs-update`, `escalate-over-shortcut`, `wrap` (the session-closing ritual: externalize memory, leave every repo clean), `reconcile-tasks`, `project-maintenance`.

**`working-method`** (6 skills) - habits applied while the work is happening, not after it: `research-first`, `running-spikes`, `pushback`, `effective-refactor`, `fast-tests`, `using-a-debugger`.

**`orchestration`** (6 skills) - what changes when work outgrows one agent, one machine, or one budget: `agent-remote`, `external-harness-routing`, `fleet-orchestration`, `review-in-parallel-pipelines`, `project-lock`, `cost-estimator`.

Each skill directory's `SKILL.md` frontmatter carries the one-line trigger description, which is the authoritative catalog.

A skill whose value collapses without a specific tool ships alongside that tool instead of living here: `capture-idea`, `find-task`, and `promote-project` at `packages/project_tracker/skills/`, `check-memory` and `memory-cleanup` at `packages/replica/skills/`, and `progress-beacon` at `satellites/agent-statusline/skills/`, all in the [schoen-lab](https://github.com/mtschoen/schoen-lab) monorepo. See [`docs/superpowers/specs/2026-08-19-reconsidering-one-repo-per-skill-design.md`](docs/superpowers/specs/2026-08-19-reconsidering-one-repo-per-skill-design.md) for the boundary reasoning behind both the family split and this placement.

## Cloning

The skills live in submodules, so a plain `git clone` will leave you with empty directories. Use one of:

```bash
# clone with submodules in one step
git clone --recursive <url>

# or, if you've already cloned without --recursive:
git submodule update --init --recursive
```

After cloning, opt this clone into recursive submodule updates so a later `git pull` keeps submodule checkouts in lockstep with the pointers the umbrella records - otherwise the umbrella drifts into a "submodule behind recorded pointer" dirty state (`M <submodule> (new commits)`):

```bash
git config submodule.recurse true
```

This lives in `.git/config` and **cannot be committed**, so run it once per clone - including on every machine you work from. It does not cover `git clone` itself (hence `--recurse-submodules` above). Trade-off: `git pull` then checks submodules out at the recorded commit (detached HEAD); `scripts/pull-all.sh` re-attaches them to `main`.

## Installing skills

`install-skills.sh` (bash) and `install-skills.bat` (Windows) copy each skill into agent skill directories. **Author skills in their family repository** (the top-level submodules in this umbrella); installed copies are generated mirrors and should not be edited directly.

`~/.agents/skills/` is the canonical runtime location read natively by **Codex** ([docs](https://developers.openai.com/codex/skills)) and **opencode** ([docs](https://opencode.ai/docs/skills)). Claude Code and Antigravity use their own runtime locations, so the installer can mirror the same tracked skill content to them. Hermes is an active destination too: it uses `<Hermes home>/skills`.

Hermes home resolution is, in order: `HERMES_HOME`, `LOCALAPPDATA/hermes` on Windows, then `~/.hermes` (or `%USERPROFILE%\.hermes` in the batch installer). With no destination flag, the installer selects only harness homes that already exist, including Hermes; it will not create unused runtime homes. Explicit destination flags and `--all` may create a missing destination.

```bash
./install-skills.sh                    # existing destinations only
./install-skills.sh -y                 # overwrite without prompting
./install-skills.sh -n                 # dry run; show what would change
./install-skills.sh --agents           # only the canonical ~/.agents/skills
./install-skills.sh --hermes smoke-test pushback  # Hermes mirror, selected skills
./install-skills.sh --all -y           # create/update every known destination
./install-skills.sh --check --hermes   # read-only drift check for Hermes
```

`--check` never prompts or writes. It exits `0` when the selected mirrors are clean, `1` when drift (including a missing destination) is found, and `2` for argument errors. It only previews symbolic `+`/`~`/`-` drift details; apply deliberately with a normal installer invocation.

Supported destination flags:

| Flag | Destination |
|---|---|
| `--agents` | `~/.agents/skills` (canonical; read natively by Codex and opencode) |
| `--claude` | `~/.claude/skills` (Claude Code mirror) |
| `--gemini` | `~/.gemini/config/skills` (Antigravity global skills directory) |
| `--hermes` | `<Hermes home>/skills` (generated Hermes mirror) |
| `--all` | all of the above; may create missing homes |

Each skill directory has `SKILL.md` at its root. The installer ships only **git-tracked** files, filtered to a top-level allowlist: `SKILL.md` + `scripts/` + `references/` + `assets/`, plus any extra top-level entries a skill declares in an optional `.skillpack` manifest at its own root. Dev-only content (`evals/`, `tests/`, `workspace/`, `README.md`, `LICENSE`, etc.) is excluded by omission, and generated junk can never leak because untracked files are never shipped.

The installer copies skill **files** only - it does not install any external runtime tooling a skill needs. Some skills have such prerequisites (e.g. `using-a-debugger` needs a debugger binary like netcoredbg/gdb/lldb/cdb plus Python 3; `cost-estimator` needs its data sources). Each such skill documents its prerequisites in its own `references/` (for `using-a-debugger`, see `references/tooling-setup.md`) and README - check there after installing.

### Hook registration (`--hooks`)

Four skills in this umbrella ship runtime hooks (`project-lock`, `progress-beacon`, `research-first`, `wrap`). Passing `--hooks` (or `--prune-hooks`) checks registration state across harness settings, offers to register unconfigured hooks, and records your yes / no / later decisions so you are asked at most once:

```bash
./install-skills.sh --hooks               # interactively offer hooks for installed skills
./install-skills.sh -y --claude --hooks   # non-interactive install + hook registration
./install-skills.sh --check --hooks       # check for unregistered hooks (drift check)
./install-skills.sh --prune-hooks         # prune dangling hooks pointing to missing skill files
```

Claude Code hooks are wired into `~/.claude/settings.json` (with automatic backup). For `project-lock`, the offer flow supports enforcement modes (`warn` recommended for initial setup, or `deny`). Decisions are recorded in `.hook-decisions.json` alongside installed skills. Harnesses without command hook contracts (Antigravity, Hermes) are reported as uncovered.

## Working across all submodules

`scripts/push-all.{sh,bat}` and `scripts/pull-all.{sh,bat}` iterate every active submodule plus the umbrella repo. push-all pushes `origin` by default; pull-all fetches + fast-forwards from `origin` only. Either accepts `--remote <name>` to add another remote where it exists. Each push is pre-flighted (fetch + classify local vs remote as up-to-date / fast-forward / behind / diverged), and non-fast-forward states are reported and skipped. Errors print inline and don't halt the run, but the script exits non-zero with a summary.

```bash
./scripts/pull-all.sh
./scripts/push-all.sh
```

## Layout

```text
skills-dev/
├── <family-name>/        # submodule -> skills-<family-name>.git
│   ├── <skill-name>/     # SKILL.md + scripts/ + references/ + assets/ + evals/ (dev-only)
│   │   └── SKILL.md      # the skill itself
│   └── ...                # one directory per skill in the family
├── install-skills.sh     # install -> selected runtime destinations
├── install-skills.bat
└── scripts/
    ├── push-all.sh
    └── pull-all.sh
```

Submodule URLs in `.gitmodules` are relative (`../skills-<family-name>.git`), resolving against whichever remote the umbrella was cloned from.

## License

MIT - see [LICENSE](LICENSE).
