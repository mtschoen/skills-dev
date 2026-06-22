# Spec: `using-a-debugger` skill

Status: approved design, pending plan. Working draft - will be distilled into the
implementation plan header and deleted at the spec -> plan handoff.

## Goal

Teach agents to drive interactive debuggers (breakpoints, stepping, reading live
program state) instead of falling back to print-debugging. Cross-platform from the
start (Windows, Linux, macOS). First languages: C# (managed) and C++ (native),
chosen because `file-wizard` is a small but real tool that has both, including a
managed-to-native P/Invoke boundary worth debugging across.

Python is explicitly out of scope for v1: the user finds breakpoint debugging less
necessary there. The skill is structured so a `references/pdb-python.md` could be
added later without reshaping the orchestrator.

## Why this shape

The user works with debuggers as live, exploratory sessions: set a breakpoint, run,
inspect memory and locals, step, poke around. The skill should let an agent work the
same way. The friction is that every agent tool call is a fresh process, so keeping
the debuggee's state alive between calls needs a long-lived driver process. That
persistent-session mechanism is the load-bearing technical risk of the whole skill,
and its viability is verified by a spike before any reference prose commits to it.

## Structure

One skill, one repo (the `skills-dev` model: each skill is its own submodule). Repo
names `skills-using-a-debugger` on Gitea (owner `schoen`, public) and GitHub
(`mtschoen/skills-using-a-debugger`, public); submodule path `using-a-debugger`.
Not a multi-skill orchestrator + satellites split - a single decision-making
`SKILL.md` plus per-topic `references/`, modeled on `fast-tests`.

```
SKILL.md                      # when to debug, mode decision, debugger selection, the loop
references/
  interactive-sessions.md     # persistent live-session technique (the hard, valuable part)
  scripted-batch.md           # reliable-default non-interactive technique
  netcoredbg-dotnet.md        # .NET managed, cross-platform
  lldb-native.md              # C/C++ native, cross-platform (macOS, Linux, Windows+clang)
  gdb-native.md               # C/C++ native, Linux-primary
  cdb-windows.md              # C/C++ native, Windows/MSVC PDB
  mixed-mode.md               # managed<->native boundary: what each toolset actually allows
  tooling-setup.md            # detect OS + installed debuggers; install-if-missing per platform
scripts/
  dbg-session.py              # persistent live-session driver (shipped if the spike proves it out)
evals/                        # skills-dev eval pattern (dev-only, not shipped)
workspace/                    # scratch (gitignored, not shipped)
README.md  LICENSE            # dev-only, not shipped (installer allowlist)
```

The installer ships only `SKILL.md` + `scripts/` + `references/` + `assets/`. If
`scripts/dbg-session.py` ships, the skill repo needs no `.skillpack` entry (scripts/
is already in the allowlist).

## The two interaction modes (core teaching)

1. **Scripted / batch** - the reliable default. Write a command file, run the
   debugger non-interactively, capture output:
   - netcoredbg: `--command=<file>` (or MI mode)
   - lldb: `lldb -b -s <file> -- <program> [args]`
   - gdb: `gdb -x <file> --batch --args <program> [args]`
   - cdb: `cdb -cf <file> <program>`
   Reproducible, no infra, works everywhere. Best for "break at a known spot, run,
   dump these values, exit." This is what the agent reaches for first.

2. **Persistent live session** - the exploration mode the user wants. A long-lived
   debugger process driven one command per tool call, with debuggee state surviving
   between calls. Implemented as `scripts/dbg-session.py`: a thin pump that owns the
   debugger subprocess and exposes send-command / read-output across separate agent
   tool calls (mechanism chosen by the spike - candidates: line-oriented stdin/stdout
   pump, GDB/MI parsing, or lldb's Python API). SKILL.md teaches **when to escalate**
   from scripted to persistent: you do not yet know where the bug is, or you need to
   interactively inspect and follow state.

The SKILL.md decision logic favors scripted first, escalates to persistent for
genuine exploration, and never silently degrades to print-debugging.

## Debugger selection and cross-platform tooling

SKILL.md carries a compact decision matrix keyed on language (managed vs native) x
platform (Windows / Linux / macOS) x available tooling, pointing at the right
reference:

- Managed (.NET): `netcoredbg` everywhere.
- Native (C/C++): `cdb` on Windows/MSVC (best PDB fidelity), `lldb` on macOS and
  Windows+clang, `gdb` on Linux (lldb also viable on Linux).

`tooling-setup.md` teaches detect-then-install: probe `PATH` and known install
locations, and if the right debugger is missing, install it per platform
(netcoredbg release artifact; cdb via Windows SDK Debugging Tools; lldb/gdb via the
platform package manager). No machine-specific hard-coded paths in shipped content -
derive from environment and platform APIs.

## Worked example and evals

`file-wizard` is the recurring concrete target:

- pure-managed flow: break in the C# CLI / `MFTLib`
- pure-native flow: break in `external/MFTLib/MFTLibNative` (C++)
- mixed-mode: step across the C#-to-native P/Invoke boundary (stretch goal)

Evals follow the `skills-dev` pattern (`evals/evals.json`, `run.py`, `grade.py`) and
exercise both interaction modes against a tiny built-from-scratch program plus
file-wizard.

## Mixed-mode position

Mixed-mode (one session stepping across the managed/native boundary) is genuinely
hard outside full Visual Studio and varies by platform and toolset. v1 ships a clean
pure-managed flow and a clean pure-native flow. Mixed-mode lands as a **fully-worked
flow only if the spike shows it is reliable** on at least one platform/toolset;
otherwise `mixed-mode.md` is an honest "here is the boundary, here is what each
toolset actually gives you, here are the realistic workarounds (for example two
attached debuggers, or break-on-native-entry from the managed side)." The user
selected file-wizard specifically to push on this, so the spike investigates it
seriously rather than assuming the limited outcome.

## Implementation phasing

Task 0 is a spike, not prose, because the design intentionally defers reference
claims to empirical findings:

- **Spike (Task 0).** Prove the persistent-session driver with `lldb` (the only
  debugger currently installed locally) on a trivial C++ program: set breakpoint,
  run, read a variable, step, read again - across separate tool calls. Decide the
  driver mechanism. Then probe mixed-mode feasibility on file-wizard per available
  toolset. Linux leg runs via the `remote-claude` skill or direct ssh to llamabox;
  macOS deferred to the user's work machine. Findings captured to
  `~/.claude/notes/spike_debugger_sessions.md`. The spike's results decide what the
  references claim and whether `dbg-session.py` ships as designed.
- **Then** the per-debugger references, `tooling-setup.md`, the two-mode SKILL.md,
  evals, and (conditionally) the mixed-mode worked flow - each grounded in verified
  technique.

## Out of scope for v1

- Python debugging (`pdb`/`debugpy`) - structure leaves room to add it later.
- GUI / IDE debuggers and DAP-client integrations beyond what a CLI driver needs.
- macOS-verified content (deferred; user tests on a work machine during the week).
