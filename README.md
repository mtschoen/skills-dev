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

After cloning, opt this clone into recursive submodule updates so a later `git pull` keeps submodule checkouts in lockstep with the pointers the umbrella records — otherwise the umbrella drifts into a "submodule behind recorded pointer" dirty state (`M <submodule> (new commits)`):

```bash
git config submodule.recurse true
```

This lives in `.git/config` and **cannot be committed**, so run it once per clone — including on every machine you work from. It does not cover `git clone` itself (hence `--recurse-submodules` above). Trade-off: `git pull` then checks submodules out at the recorded commit (detached HEAD); `scripts/pull-all.sh` re-attaches them to `main`.

## Installing skills

`install-skills.sh` (bash) and `install-skills.bat` (Windows) copy each skill into agent skill directories. The canonical source of truth is `~/.agents/skills/`, which **Codex** ([docs](https://developers.openai.com/codex/skills)) and **opencode** ([docs](https://opencode.ai/docs/skills/)) both read natively as a global skills path. Two harnesses can't read it and so are kept as mirrors:

- **Claude Code** is hardcoded to `~/.claude/skills/` with no setting to redirect it ([anthropics/claude-code#22902](https://github.com/anthropics/claude-code/issues/22902), [#33957](https://github.com/anthropics/claude-code/issues/33957)).
- **Antigravity** loads global skills from `~/.gemini/skills/`; its `.agents/skills` is workspace-only.

So the default install writes to all three — `~/.agents/skills/` plus mirrors at `~/.claude/skills/` and `~/.gemini/skills/` — rather than relying on symlinks. Pass agent flags to narrow the targets.

```bash
./install-skills.sh           # default: ~/.agents/skills + ~/.claude/skills + ~/.gemini/skills
./install-skills.sh -y        # overwrite without prompting
./install-skills.sh -n        # dry run; show what would change
./install-skills.sh --agents  # only the canonical ~/.agents/skills
./install-skills.sh --claude smoke-test pushback   # limit destinations and skills
```

Supported destination flags:

| Flag | Destination |
|---|---|
| `--agents` | `~/.agents/skills` (canonical; read natively by Codex and opencode) |
| `--claude` | `~/.claude/skills` (Claude Code's mirror) |
| `--gemini` | `~/.gemini/skills` (Antigravity's global skills dir) |
| `--all` | all of the above |

Each skill directory either has `SKILL.md` at its root (new layout) or a `skill-draft/` subdirectory (legacy layout). The installer detects which and copies the right content; dev-only files (`evals/`, `docs/`, `README.md`, `.gitea/`, `.markdownlint-cli2.jsonc`, etc.) are excluded for the root layout.

## Working across all submodules

`scripts/push-all.{sh,bat}` and `scripts/pull-all.{sh,bat}` iterate every active submodule plus the umbrella repo and push/pull against `origin` by default. Pass `--remote <name>` to also push/pull another remote where it exists. Errors print inline and don't halt the run.

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
├── install-skills.sh    # install -> ~/.agents/skills/ (+ Claude & Antigravity mirrors)
├── install-skills.bat
└── scripts/
    ├── push-all.sh
    └── pull-all.sh
```

Submodule URLs in `.gitmodules` are relative (`../skills-<name>.git`), so the same `.gitmodules` works whether you cloned from Gitea or GitHub.

## License

MIT — see [LICENSE](LICENSE).
