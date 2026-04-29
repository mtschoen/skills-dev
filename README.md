# skills-dev

A workspace for developing [Claude Code](https://claude.com/claude-code) skills. Each top-level directory is a git submodule pointing at that skill's own repository; this repo is the umbrella that ties them together and provides install + sync tooling.

## Cloning

The skills live in submodules, so a plain `git clone` will leave you with empty directories. Use one of:

```bash
# clone with submodules in one step
git clone --recursive <url>

# or, if you've already cloned without --recursive:
git submodule update --init --recursive
```

## Installing skills

`install-skills.sh` (bash) and `install-skills.bat` (Windows) copy each skill into `~/.claude/skills/` so Claude Code picks them up.

```bash
./install-skills.sh           # interactive: prompts before overwriting changed installs
./install-skills.sh -y        # overwrite without prompting
./install-skills.sh -n        # dry run; show what would change
./install-skills.sh smoke-test pushback   # limit to specific skills
```

Each skill directory either has `SKILL.md` at its root (new layout) or a `skill-draft/` subdirectory (legacy layout). The installer detects which and copies the right content; dev-only files (`evals/`, `docs/`, `README.md`, etc.) are excluded for the root layout.

## Working across all submodules

`scripts/push-all.{sh,bat}` and `scripts/pull-all.{sh,bat}` iterate every active submodule plus the umbrella repo and push/pull against both `origin` (Gitea) and `github` (GitHub) where those remotes exist. Errors print inline and don't halt the run.

```bash
./scripts/pull-all.sh
./scripts/push-all.sh
```

## Layout

```
skills-dev/
├── <skill-name>/        # submodule -> skills-<skill-name>.git
│   ├── SKILL.md         # the skill itself
│   ├── evals/           # eval harness (dev-only, not installed)
│   └── ...
├── install-skills.sh    # install -> ~/.claude/skills/
├── install-skills.bat
└── scripts/
    ├── push-all.sh
    └── pull-all.sh
```

Submodule URLs in `.gitmodules` are relative (`../skills-<name>.git`), so the same `.gitmodules` works whether you cloned from Gitea or GitHub.

## License

MIT — see [LICENSE](LICENSE).
