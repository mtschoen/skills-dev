# Installer allowlist rework — design

**Date:** 2026-05-24
**Status:** spec (working draft — distilled into the plan header at handoff, then deleted)

## Goal

Stop the installer from shipping junk (`__pycache__`, `.pytest_cache`, stray
dev files) into the agent skills dirs, and have it actively remove cruft left
by prior installs. Replace the failing exclude-list (denylist) approach with a
git-native allowlist that cannot leak untracked files by construction. No new
runtime dependency.

## Root cause (why the current installer leaks)

The installer copies the **working tree** of each skill (`tar` on bash,
`robocopy` on batch). Two failure modes follow:

1. **Untracked junk ships.** The worst offenders are *gitignored* and therefore
   invisible to the exclude lists unless someone remembers to name each one:
   - `__pycache__`, `.pytest_cache`, `reports/` are gitignored (confirmed via
     `git check-ignore`) yet got copied into `~/.claude/skills/cost-estimator/`.
   - The exclude list is a denylist: every new kind of generated file leaks
     until it's manually added. This is the approach that's failing.

2. **Stale dest dirs are pinned, not cleaned.** On Windows the batch script runs
   `robocopy /MIR /XD <excluded>`. `/XD` protects an excluded directory *in the
   destination* from `/MIR`'s purge. So once `reports/` was installed (before it
   was excluded), adding it to the exclude list can never remove it — the
   exclusion that's meant to keep it out actually keeps the stale copy alive.

## Design

### 1. Ship only git-tracked files, at working-tree content

For each skill the installer derives the file set from `git -C <skill> ls-files`
rather than walking the filesystem. `ls-files` lists tracked paths only, so the
entire category of "generated junk we forgot to exclude" is eliminated
structurally — an untracked file is never a candidate.

Files are copied from the **working tree** (not `git archive HEAD`), so
uncommitted local edits to a skill still install. This preserves the
edit → install → test loop; `git archive HEAD` was rejected because it would
silently install stale committed content when the dev has unstaged changes.

Git is already a hard dependency (the skills are submodules), so this adds
nothing to the install prerequisites.

### 2. Top-level allowlist

A tracked file ships iff its **top-level path component** is in the include set:

- **Baseline (every skill):** `SKILL.md`, `scripts/`, `references/`, `assets/`
  — the Agent Skills convention plus the required SKILL.md.
- **Per-skill manifest** adds extra top-level entries where a skill legitimately
  needs content outside the convention.

Because the restructure (§4) keeps `scripts/` runtime-only, the allowlist is
purely top-level — no glob pruning *within* an included directory is needed
anywhere. Tracked dev content (`tests/`, `evals/`, `README.md`, `.gitea/`,
`.gitignore`, `.markdownlint-cli2.jsonc`, screenshots, the manifest file itself)
is simply absent from the include set and is therefore dropped automatically.

### 3. Per-skill manifest

A small, optional file at each skill's repo root listing **extra top-level
entries to include beyond the baseline**, one per line, `#` comments allowed.
Format is line-based (not JSON/YAML) so both bash and batch parse it trivially.

Proposed filename: `.skillpack` (installer-specific metadata, clearly ours, not
an Agent Skills artifact). The file is not in the baseline include set and never
lists itself, so it is auto-excluded from installs.

Only two skills need one:

```
# progress-beacon/.skillpack
hooks/

# cost-estimator/.skillpack
REPORT_TEMPLATE.md
```

No `ignore` directive is introduced (YAGNI — the restructure removes the only
nested-prune case). The format can grow an `ignore` verb later if a skill ever
needs it.

### 4. Restructure cost-estimator: `scripts/` runtime-only

`cost-estimator/scripts/` currently mixes runtime scripts with dev-only ones
(`test_*.py`, `run-tests.{sh,bat}`, `regen-screenshots.{sh,bat}`,
`capture-screenshot.py`). Move the dev-only files out so `scripts/` ships
wholesale with no per-file decisions:

- `test_*.py` → `tests/`
- `run-tests.{sh,bat}` → `tests/` (or a `dev/` dir)
- `regen-screenshots.{sh,bat}`, `capture-screenshot.py` → `dev/`

**Caveat (must not break the tests):** the tests load runtime scripts via
`Path(__file__).parent / "<script>.py"` (e.g. `test_resolve_roots.py` loads
`analyze-month.py`). After moving tests out of `scripts/`, these path references
must be updated (e.g. `Path(__file__).parent.parent / "scripts" / "..."`) and
`pytest` re-run to confirm green. This is a distinct work item in the
cost-estimator submodule with its own verification, committed separately.

### 5. Staging + mirror (cleanup falls out for free)

For each skill/destination:

1. Build the shippable set (allowlist applied to `git ls-files`) into a temp
   **staging** dir, copying from the working tree.
2. **Mirror** staging → dest:
   - bash: `rsync -a --delete staging/ dest/` (fallback: `rm -rf dest && cp`),
     or a tar-pipe with explicit removal of dest extras.
   - batch: `robocopy staging dest /MIR` — over an *already-clean* staging tree,
     so it runs with **no `/XD`** and the dest-pinning bug cannot occur.
3. The set difference `dest \ staging` is the **removal list** — exactly the
   prior-install cruft. On the first run of the new installer, leaked
   `__pycache__`, `reports/`, screenshots, etc. surface here as removals.

### 6. Diff preview, dry-run, confirm

Preserve current UX:

- Show adds / changes / **removals** before applying (`robocopy /L` on batch,
  `diff -rq staging dest` on bash).
- `-n` / `--dry-run` previews without applying.
- `-y` / confirm gate before mutating an existing dest, per current behavior.

### 7. Implementation: keep dual bash + batch

At this complexity (git produces the file list; the allowlist is a top-level
prefix filter over a flat list; the mirror is `rsync --delete` / `robocopy /MIR`
over clean staging) the dual-script approach stays small and avoids a Python
runtime dependency on the installer entry points. Estimated ~+50 lines bash,
~+80 lines batch versus today. Python single-source was considered and rejected
specifically to avoid the added dependency.

## Migration

No explicit migration step. The first run of the new installer over existing
installs reconciles each dest to its clean staging set — the accumulated cruft
(`__pycache__`, `.pytest_cache`, `reports/`, `screenshot*.png`, the dev scripts)
is reported as removals and purged on confirm / `-y`.

## Non-goals

- Python rewrite of the installer (rejected: avoid the dependency).
- Consolidating `scripts/{push,pull}-all.{sh,bat}` (separate pending decision).
- An `ignore` manifest verb (not needed after the restructure).
- Changing `validate_skills.py` / CI (confirmed it doesn't touch the excludes).

## Testing

- **Dry-run parity:** `install-skills.{sh,bat} -n` over all skills lists the
  expected adds/removals; the leaked junk appears as removals.
- **Clean install:** install to a throwaway dest; assert no `__pycache__`,
  `.pytest_cache`, `tests/`, `README.md`, screenshots, or `.skillpack` present;
  assert `SKILL.md` + runtime `scripts/` present; `hooks/` present for
  progress-beacon; `REPORT_TEMPLATE.md` present for cost-estimator.
- **Cleanup:** seed a dest with stale `reports/` + `__pycache__`, run installer,
  assert they're removed (proves the `/XD` bug is fixed).
- **Uncommitted edit:** modify a tracked SKILL.md without committing, install,
  assert the edit propagates (proves working-tree content, not `HEAD`).
- **cost-estimator restructure:** `pytest` green after moving tests.
- **Cross-platform:** run both `.sh` (llamabox / git-bash) and `.bat` (Windows).

## Open question

- Manifest filename: `.skillpack` proposed. Confirm or pick another (e.g.
  `install-include.txt`, `.skill-install`).
