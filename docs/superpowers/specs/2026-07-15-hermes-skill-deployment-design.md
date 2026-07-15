# Hermes Skill Deployment Design

## Goal

Extend the source-first `skills-dev` deployment workflow so Hermes Agent receives the same tracked skill payloads as the existing Agents, Claude Code, and Gemini destinations. Add an automated drift check without creating a second packaging implementation.

## Source of truth

The authoritative skill content remains each `skills-dev/<skill>` source repository. Runtime directories are generated deployments. No shared skill may be edited in the Hermes runtime directory and treated as durable.

Hermes will be another destination in `install-skills.sh` and `install-skills.bat`, not a plugin. Hermes plugin installation uses a shallow clone without recursive submodule initialization, so installing the umbrella as a plugin would omit every source skill.

## Destination resolution

Both installers gain `--hermes` and include Hermes in `--all`.

The Bash installer resolves the Hermes home in this order:

1. `HERMES_HOME`, when non-empty.
2. On Windows or MSYS, `$LOCALAPPDATA/hermes` when `LOCALAPPDATA` is available.
3. `$HOME/.hermes` on other platforms.

When `cygpath` is available, native Windows environment paths are normalized for Bash filesystem operations. The destination is `<Hermes home>/skills`.

The batch installer resolves the home in this order:

1. `%HERMES_HOME%`, when defined.
2. `%LOCALAPPDATA%\hermes`.
3. `%USERPROFILE%\.hermes` as a defensive fallback.

Default mode retains the established existing-only behavior: Hermes is selected automatically only when its home directory already exists. Explicit `--hermes` and `--all` create a missing destination.

## Drift detection

Both installers gain `--check`.

`--check` implies dry-run behavior and never prompts or writes. It checks the destinations selected by the usual destination flags and skill filters. It exits:

- `0` when every selected deployed skill matches its source payload.
- `1` when any selected skill is missing or differs.
- `2` for argument errors.

The normal symbolic preview remains the human-readable drift report. This reuses the installers' existing allowlist, `.skillpack`, tracked-file, and generated-output preservation semantics instead of creating a second scanner that could drift from deployment behavior.

## Git Bash prerequisite repair

The current Windows baseline has 17 failing Bash-installer tests. The installer passes MSYS paths such as `/tmp/...` directly to Windows `git.exe` through `git -C`; that executable cannot resolve the path. The failed `git ls-files` occurs in process substitution, so `set -e` does not stop the script and an empty destination is reported as success.

Add a small helper that converts only Git working-directory arguments through `cygpath -w` when available. Make staging fail when `git ls-files` fails instead of silently installing an empty payload. This is a prerequisite bug fix, committed separately before Hermes behavior.

## Documentation

Update `README.md` and both installers' help text to describe:

- `skills-dev` repositories as the authoring source.
- `~/.agents/skills` as the canonical shared runtime destination for harnesses that read it natively.
- Hermes as a generated mirror.
- `--hermes`, `--all`, default existing-only behavior, and `--check`.

Do not add machine-specific absolute paths.

## Testing

Follow red-green-refactor.

1. Use the existing failing Windows installer tests to prove the Git working-directory bug, then make the complete existing suite green.
2. Add Bash-installer tests for help, explicit Hermes installation, default existing-only selection, `--all`, and `--check` clean/drift exit codes.
3. Extend `tests/test-install.sh` with batch-installer Hermes installation and check-mode coverage using temporary homes.
4. Run the umbrella gates: pytest, shell test, Ruff lint and format, ShellCheck when available, changed-file Aislop, and `git diff --check`.
5. Run a real dry-run/check against the installed Hermes destination without overwriting it.

## Error handling and safety

- Missing source `SKILL.md` remains a skip.
- A failed source file enumeration is fatal, not an empty successful install.
- Check mode has no write path.
- Existing generated-output exclusions remain unchanged.
- The implementation must not modify source skill submodule pointers.
