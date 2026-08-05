# skills-dev

A workspace for developing agent skills - reusable capabilities for AI coding assistants including Codex, opencode, [Claude Code](https://claude.com/claude-code), Antigravity, and Hermes. Each top-level directory is a git submodule pointing at that skill's own repository; this repo is the umbrella that ties them together and provides install + sync tooling.

## Cloning

The skills live in submodules, so a plain `git clone` will leave you with empty directories. Use one of:

```bash
# clone with submodules in one step
git clone --recursive <url>

# or, if you've already cloned without --recursive:
git submodule update --init --recursive
```

After cloning, opt this clone into recursive submodule updates so a later `git pull` keeps submodule checkouts in lockstep with the pointers the umbrella records — otherwise the umbrella drifts into a "submodule behind recorded pointer" dirty state (`M <submodule> (new commits)`):

```bash
git config submodule.recurse true
```

This lives in `.git/config` and **cannot be committed**, so run it once per clone — including on every machine you work from. It does not cover `git clone` itself (hence `--recurse-submodules` above). Trade-off: `git pull` then checks submodules out at the recorded commit (detached HEAD); `scripts/pull-all.sh` re-attaches them to `main`.

## Installing skills

`install-skills.sh` (bash) and `install-skills.bat` (Windows) copy each skill into agent skill directories. **Author skills in their own source repositories** (the top-level submodules in this umbrella); installed copies are generated mirrors and should not be edited directly.

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

Each skill repo has `SKILL.md` at its root. The installer ships only **git-tracked** files, filtered to a top-level allowlist: `SKILL.md` + `scripts/` + `references/` + `assets/`, plus any extra top-level entries a skill declares in an optional `.skillpack` manifest at its repo root. Dev-only content (`evals/`, `tests/`, `workspace/`, `README.md`, `LICENSE`, etc.) is excluded by omission, and generated junk can never leak because untracked files are never shipped.

## Working across all submodules

`scripts/push-all.{sh,bat}` and `scripts/pull-all.{sh,bat}` iterate every active submodule plus the umbrella repo. push-all pushes to both `origin` (Gitea) and `github` (GitHub) by default; pull-all fetches + fast-forwards from `origin` only. Either accepts `--remote <name>` to add another remote where it exists. Each push is pre-flighted (fetch + classify local vs remote as up-to-date / fast-forward / behind / diverged), and non-fast-forward states are reported and skipped. Errors print inline and don't halt the run, but the script exits non-zero with a summary.

```bash
./scripts/pull-all.sh
./scripts/push-all.sh
./scripts/pull-all.sh --remote github
./scripts/push-all.sh --remote github
```

## Layout

```text
skills-dev/
├── <skill-name>/        # submodule -> skills-<skill-name>.git
│   ├── SKILL.md         # the skill itself
│   ├── evals/           # eval harness (dev-only, not installed)
│   └── ...
├── install-skills.sh    # install -> selected runtime destinations
├── install-skills.bat
└── scripts/
    ├── push-all.sh
    └── pull-all.sh
```

Submodule URLs in `.gitmodules` are relative (`../skills-<name>.git`), so the same `.gitmodules` works whether you cloned from Gitea or GitHub.

## License

MIT — see [LICENSE](LICENSE).
