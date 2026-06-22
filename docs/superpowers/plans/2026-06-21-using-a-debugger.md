# using-a-debugger Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform `using-a-debugger` skill that teaches agents to drive interactive debuggers (breakpoints, stepping, reading live program state) for C# (netcoredbg) and C++ (lldb / gdb / cdb), with `file-wizard` as the worked example.

**Architecture:** One skill, one repo (the skills-dev submodule model), shaped like `fast-tests`: a decision-making `SKILL.md` orchestrator plus per-debugger `references/`. Two interaction modes are taught - scripted/batch (reliable default) and a persistent live session driven by a shipped client/server script (`scripts/dbg-session.py`) so debuggee state survives across separate agent tool calls. A spike (Phase 0) verifies the persistent-session mechanism and probes mixed-mode feasibility before any reference prose commits to claims.

**Tech Stack:** Markdown skill content; Python 3 (stdlib only) for the session driver and evals; debuggers lldb (installed at `C:\Program Files\LLVM\bin\lldb`), gdb, cdb (Windows SDK), netcoredbg; `dotnet` 10.0.300; clang for trivial native test targets.

## Global Constraints

- **No em-dashes** in any generated content (prose, code, comments, commit messages). Use ` - `, `:`, or parens. ASCII only.
- **No machine-specific hard-coded paths** in shipped content (`SKILL.md`, `references/`, `scripts/`). Derive from `PATH`, env vars, platform APIs, or arguments. Machine paths are fine only in the dev-only spike note and in non-shipped `evals/`/`workspace/`.
- **Cross-platform**: Windows, Linux, macOS. macOS content stays unverified until the user tests on a work machine; mark such content `(unverified on macOS)`.
- **Repo naming**: Gitea `schoen/skills-using-a-debugger` (public), GitHub `mtschoen/skills-using-a-debugger` (public), submodule path `using-a-debugger`. Per skills-dev `CLAUDE.md` "Adding a new skill".
- **Installer allowlist**: only `SKILL.md` + `scripts/` + `references/` + `assets/` ship. `evals/`, `workspace/`, `README.md`, `LICENSE` are dev-only. No `.skillpack` needed (driver lives under `scripts/`).
- **Python style**: stdlib only (no third-party deps in shipped `scripts/`); ruff-clean (the skill repo inherits markdownlint + agentskills validate CI, not pytest - driver tests are local-run).
- **Skill-authoring discipline**: follow `superpowers:writing-skills` for `SKILL.md` frontmatter (`name`, `description` with concrete triggers) and reference structure.

---

## Phase 0: Spike - verify the load-bearing mechanisms

This phase produces a findings note, not skill content. It gates every later claim. Author nothing in `references/` until it completes. Work in a scratch dir, not the skill tree.

### Task 0.1: Persistent-session viability with lldb

**Files:**
- Create (dev-only, scratch): `~/debugger-spike/hello.cpp`, `~/debugger-spike/probe_lldb.py`
- Create (findings): `~/.claude/notes/spike_debugger_sessions.md`

**Goal of the spike:** answer, with running code, "can an agent hold a live lldb session across separate process invocations, set a breakpoint, run, read a local, step, and read it again?" The candidate mechanism is a **client/server**: a long-lived server process owns `lldb` via piped stdin/stdout and delimits each command's output with a unique marker; short-lived client calls (one per agent tool call) talk to it over a localhost socket.

- [ ] **Step 1: Build a trivial debuggable C++ target**

`~/debugger-spike/hello.cpp`:

```cpp
#include <cstdio>
int add(int a, int b) {
    int sum = a + b;   // breakpoint target
    return sum;
}
int main() {
    for (int i = 0; i < 3; ++i) {
        int r = add(i, i * 2);
        printf("r=%d\n", r);
    }
    return 0;
}
```

Build with debug info:
```bash
clang++ -g -O0 -o ~/debugger-spike/hello ~/debugger-spike/hello.cpp   # Windows: hello.exe
```
Expected: a `hello` binary plus PDB/dwarf debug info. If `clang++` is absent, install LLVM/clang (already present locally per `C:\Program Files\LLVM`).

- [ ] **Step 2: Probe whether lldb cooperates over piped stdin/stdout (the buffering risk)**

`~/debugger-spike/probe_lldb.py` - launch lldb with pipes, send commands, marker-delimit output, confirm a breakpoint hit and a variable read work non-interactively:

```python
import subprocess, sys, threading, queue, os
LLDB = os.environ.get("LLDB", "lldb")
prog = os.path.expanduser("~/debugger-spike/hello")
p = subprocess.Popen([LLDB, "--no-use-colors", prog],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT, text=True, bufsize=1)
q = queue.Queue()
threading.Thread(target=lambda: [q.put(l) for l in p.stdout], daemon=True).start()

def send(cmd, token):
    p.stdin.write(cmd + "\n")
    p.stdin.write(f'script print("{token}")\n')
    p.stdin.flush()
    out = []
    while True:
        line = q.get(timeout=20)
        if line.strip() == token:
            return "".join(out)
        out.append(line)

print(send("breakpoint set --file hello.cpp --line 3", "T1"))
print(send("run", "T2"))
print(send("frame variable a b", "T3"))   # expect a/b values at first hit
print(send("expression sum = -1", "T4"))
print(send("continue", "T5"))
p.stdin.write("quit\n"); p.stdin.flush()
```

Run: `python ~/debugger-spike/probe_lldb.py`
Expected PASS: T2 shows "stop reason = breakpoint", T3 prints `a` and `b` integer values, T5 continues to program output. If lldb buffers and the marker never arrives (pipe needs a pty), record that and try the fallback (Step 3).

- [ ] **Step 3: If pipes fail, test the lldb Python-API fallback**

Only if Step 2 hangs/buffers: probe `import lldb` (the SB API) driving the same flow programmatically (`SBDebugger.Create()`, `CreateTargetWithFileAndArch`, `BreakpointCreateByLocation`, `LaunchSimple`, read `SBFrame.FindVariable`). Record whether the SB API is importable from the system Python and whether it is the more robust server backend.

- [ ] **Step 4: Decide the driver mechanism and record findings**

Write `~/.claude/notes/spike_debugger_sessions.md` (frontmatter `type: reference`) answering:
1. Does the piped-stdin + marker mechanism work for lldb? (yes/no + evidence)
2. If no, is the SB Python API the backend? (yes/no)
3. Chosen server backend for Phase 1 (`pipe+marker` or `sb-api`).
4. Per-debugger marker command that forces a delimiter line: lldb `script print("TOKEN")`, gdb `echo TOKEN\n`, cdb `.echo TOKEN`, netcoredbg (to be confirmed in Task 0.3).
5. Observed gotchas (color codes, prompt echoing, flush behavior).

Add a one-line pointer in `~/.claude/notes/MEMORY.md` under References.

- [ ] **Step 5: Commit the spike note** (in the agent-memory repo, not skills-dev)

```bash
git -C ~/.claude/notes add spike_debugger_sessions.md MEMORY.md
git -C ~/.claude/notes commit -m "spike: persistent debugger session mechanism (lldb)"
```

### Task 0.2: Linux cross-check (gdb + lldb) via llamabox

**Files:** reuse the scratch probe, run on llamabox.

- [ ] **Step 1: Run the same probe on Linux**

Use the `remote-claude` skill (or `ssh llamabox`) to copy `hello.cpp` + `probe_lldb.py`, build with `g++ -g -O0` and `clang++ -g -O0`, and run the probe against both `gdb` and `lldb`. For gdb, swap the marker line to `echo @@TOKEN@@\n` and the launch argv to `gdb --nx --quiet prog`.
Expected: confirm pipe+marker works (or does not) on Linux for each. Linux is the platform where gdb is primary, so this validates the gdb adapter early.

- [ ] **Step 2: Append Linux findings** to `spike_debugger_sessions.md` (per-debugger, per-platform table). Commit.

### Task 0.3: netcoredbg + mixed-mode feasibility probe

**Files:** scratch dir; findings appended to the spike note.

- [ ] **Step 1: Acquire netcoredbg**

netcoredbg is not installed. Download the release artifact for the platform (https://github.com/Samsung/netcoredbg/releases) into a scratch dir (do NOT hard-code its path into shipped content; `tooling-setup.md` will teach discovery). Confirm `netcoredbg --version`.

- [ ] **Step 2: Probe netcoredbg CLI + marker mechanism**

Build a trivial `dotnet new console` app (`dotnet build -c Debug`). Launch `netcoredbg --interpreter=cli -- dotnet bin/Debug/.../app.dll` over pipes; determine the command that forces a delimiter line (try `print "TOKEN"` / MI mode `--interpreter=mi` with its `(gdb)`/`^done` framing). Record the working marker + whether CLI or MI is the better server backend for .NET.

- [ ] **Step 3: Mixed-mode reality check on file-wizard**

Build file-wizard per its `AGENTS.md` dual-toolchain steps (VS MSBuild for `MFTLibNative.vcxproj`, `dotnet build` for managed). Then, on each available platform/toolset, probe whether a single debugger can follow the C# -> native P/Invoke into `MFTLibNative.dll` with symbols:
- netcoredbg: managed-only? Confirm it cannot step into native (expected).
- cdb/windbg (after install in Phase 2): can it break on the native export and show C++ frames while the managed side is stopped?
- lldb on a clang-built native lib: does it see native frames called from the runtime?
Record per-toolset what mixed-mode actually yields, and a verdict: **fully-worked flow** (if one toolset reliably crosses the boundary) vs **honest-limits reference**.

- [ ] **Step 4: Append findings + commit.** This decides Task 3.2's shape.

**PHASE 0 GATE:** Do not start Phase 1 until `spike_debugger_sessions.md` records (a) the chosen server backend and (b) the mixed-mode verdict.

---

## Phase 1: Skill scaffold + persistent-session driver

Author content in a local `using-a-debugger/` directory inside skills-dev, made into **its own git repo at Task 1.1** (the submodule conversion in Phase 4 pushes this history to Gitea/GitHub and re-adds it as a submodule; it does NOT re-init). **Working-directory convention for Phases 1-3:** all `git add`/`git commit` commands below run from **inside the `using-a-debugger/` repo**, with paths relative to it (drop the leading `using-a-debugger/` shown for clarity). All driver code is stdlib-only Python.

**Architecture (set by the Phase 0 spike - see `~/.claude/notes/spike_debugger_sessions.md`).** The persistent driver is a client/server: a long-lived **server** owns a **Backend** (one debugger process) and answers a short-lived **client** over a localhost socket, so the debuggee's state survives across agent tool calls. The agent speaks a **uniform verb language** (`break file:line`, `run`, `continue`, `step`, `stepin`, `local NAME`, `bt`, `raw <native>`); each Backend translates verbs to its debugger's native protocol. Three backend families, because the spike proved their I/O models genuinely differ:

| Backend | Debuggers | Transport | Stop handling | Locals |
|---|---|---|---|---|
| `MiBackend` | netcoredbg, gdb | pipe (netcoredbg); PTY on Unix (gdb) | self-framing: gate on `*stopped`, drain to `(gdb)`; skip first `entry-point-hit` (netcoredbg) | `-var-create NAME * NAME` |
| `LldbCliBackend` | lldb | pipe | async: read until `stop reason =\|Process \d+ exited`, THEN send `script print(TOKEN)` marker | `frame variable NAME` |
| `CdbBackend` | cdb | pipe | synchronous prompt `0:000> `; marker `.echo TOKEN` | `dv NAME` / `dx` |

Cross-cutting: Backends share a `Transport` (pipe vs PTY) and a working-binary `discovery` step (the spike found the Windows system LLVM lldb is broken - must locate a CLion-bundled lldb; cdb must be installed first). Verb -> native translation tables and all gating constants come verbatim from the spike note.

### Task 1.1: Scaffold the skill directory

**Files:**
- Create: `using-a-debugger/SKILL.md` (stub), `using-a-debugger/README.md`, `using-a-debugger/.gitignore`, `using-a-debugger/scripts/dbgsession/__init__.py`

- [ ] **Step 0: Initialize the skill repo**

```bash
mkdir -p using-a-debugger && cd using-a-debugger && git init -b main && cd ..
```
All Phase 1-3 commits land in this repo (run them from inside `using-a-debugger/`).

- [ ] **Step 1: Create the directory tree and a SKILL.md frontmatter stub**

`using-a-debugger/SKILL.md` (body filled in Task 2.4; frontmatter now so the tree validates):
```markdown
---
name: using-a-debugger
description: "Use when a bug needs more than print statements - set breakpoints, step, and read live program state in C#/C++ (and similar native/managed runtimes). Covers scripted/batch debugging and a persistent live-session driver, cross-platform (lldb/gdb/cdb/netcoredbg). Triggers: a crash or wrong value you cannot localize by reading code, an exception with no clear origin, or wanting to inspect memory/locals at a specific point."
---

# Using a Debugger

(stub - body authored in Task 2.4)
```

`using-a-debugger/.gitignore`:
```
workspace/
__pycache__/
*.pyc
```

Run: `ls using-a-debugger/scripts/dbgsession/__init__.py`
Expected: file exists (empty package init).

- [ ] **Step 2: Commit**
```bash
git add using-a-debugger/SKILL.md using-a-debugger/README.md using-a-debugger/.gitignore using-a-debugger/scripts/dbgsession/__init__.py
git commit -m "scaffold: using-a-debugger skill tree"
```

### Task 1.2: Transport layer (pipe + PTY)

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/transport.py`
- Test: `using-a-debugger/scripts/dbgsession/test_transport.py`

**Interfaces:**
- Produces: `open_transport(argv: list[str], kind: str) -> Transport` where `kind in {"pipe","pty"}`. `Transport` has `write(s: str) -> None`, `read_until(predicate, timeout) -> str` (accumulates output, returns once `predicate(acc)` is true; raises `TimeoutError`), `close() -> None`. Consumed by every Backend.
- `PtyTransport` is POSIX-only (`pty.openpty`, `os.read`); `open_transport(..., "pty")` on Windows raises `RuntimeError`. Spike fact: gdb's CLI deadlocks on a plain pipe, so on Unix gdb gets `"pty"`.

- [ ] **Step 1: Write the failing test** (`test_transport.py`)

```python
import os, sys, pytest
from transport import open_transport

ECHO = [sys.executable, "-u", "-c",
        "import sys\nfor line in sys.stdin:\n sys.stdout.write('GOT:'+line); sys.stdout.flush()"]

def test_pipe_read_until_marker():
    t = open_transport(ECHO, "pipe")
    try:
        t.write("hello\n")
        out = t.read_until(lambda acc: "GOT:hello" in acc, timeout=10)
        assert "GOT:hello" in out
    finally:
        t.close()

def test_pipe_read_until_times_out():
    t = open_transport(ECHO, "pipe")
    try:
        with pytest.raises(TimeoutError):
            t.read_until(lambda acc: "NEVER" in acc, timeout=1)
    finally:
        t.close()

@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_pty_available_on_posix():
    t = open_transport(ECHO, "pty")
    try:
        t.write("hi\n")
        assert "GOT:hi" in t.read_until(lambda acc: "GOT:hi" in acc, timeout=10)
    finally:
        t.close()

def test_pty_rejected_on_windows():
    if os.name == "nt":
        with pytest.raises(RuntimeError):
            open_transport(ECHO, "pty")
```

- [ ] **Step 2: Run, verify it fails** - `cd using-a-debugger/scripts/dbgsession && python -m pytest test_transport.py -q` -> FAIL (no module `transport`).

- [ ] **Step 3: Implement `transport.py`**

Reference implementation (must satisfy the tests and the spike-verified behavior: pipe uses a reader thread + queue; pty uses `os.read` on the master fd and strips command echo / `\r` / ANSI):

```python
import os, queue, re, subprocess, threading, time
from typing import Callable

_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class Transport:
    def write(self, s: str) -> None: raise NotImplementedError
    def read_until(self, predicate: Callable[[str], bool], timeout: float) -> str: raise NotImplementedError
    def close(self) -> None: raise NotImplementedError


class PipeTransport(Transport):
    def __init__(self, argv):
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.p.stdout:
            self.q.put(line)

    def write(self, s):
        self.p.stdin.write(s); self.p.stdin.flush()

    def read_until(self, predicate, timeout):
        acc, deadline = "", time.monotonic() + timeout
        while True:
            if predicate(acc):
                return acc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"read_until timed out; acc so far:\n{acc}")
            try:
                acc += self.q.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                pass

    def close(self):
        try: self.p.kill()
        except Exception: pass


class PtyTransport(Transport):
    def __init__(self, argv):
        if os.name == "nt":
            raise RuntimeError("PtyTransport is POSIX-only")
        import pty
        self.master, slave = pty.openpty()
        self.p = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)

    def write(self, s):
        os.write(self.master, s.encode())

    def read_until(self, predicate, timeout):
        import select
        acc, deadline = "", time.monotonic() + timeout
        while True:
            if predicate(acc):
                return acc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"read_until timed out; acc so far:\n{acc}")
            r, _, _ = select.select([self.master], [], [], min(remaining, 0.5))
            if r:
                try:
                    chunk = os.read(self.master, 4096).decode(errors="replace")
                except OSError:
                    return acc
                acc += _ANSI.sub("", chunk.replace("\r", ""))

    def close(self):
        try: self.p.kill()
        except Exception: pass
        try: os.close(self.master)
        except Exception: pass


def open_transport(argv, kind):
    if kind == "pipe":
        return PipeTransport(argv)
    if kind == "pty":
        return PtyTransport(argv)
    raise ValueError(f"unknown transport kind: {kind}")
```

- [ ] **Step 4: Run, verify pass** - `python -m pytest test_transport.py -q` -> PASS (pty tests skip on Windows).
- [ ] **Step 5: Commit** - `git add scripts/dbgsession/transport.py scripts/dbgsession/test_transport.py && git commit -m "feat(driver): pipe + pty transport layer"`

### Task 1.3: MI mini-parser

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/miparse.py`
- Test: `using-a-debugger/scripts/dbgsession/test_miparse.py`

**Interfaces:**
- Produces: `parse_mi_line(line: str) -> dict` returning `{"kind": "result"|"async"|"stream"|"prompt", "class": str, "fields": dict}`. Examples: `*stopped,reason="breakpoint-hit"` -> `{"kind":"async","class":"stopped","fields":{"reason":"breakpoint-hit"}}`; `(gdb)` -> `{"kind":"prompt"}`; `^done,name="a",value="0"` -> `{"kind":"result","class":"done","fields":{"name":"a","value":"0"}}`. Stdlib only, hand-rolled (NOT pygdbmi). Consumed by `MiBackend`.

- [ ] **Step 1: Write the failing test** (`test_miparse.py`) - cases drawn verbatim from the spike note:

```python
from miparse import parse_mi_line

def test_prompt():
    assert parse_mi_line("(gdb)")["kind"] == "prompt"

def test_stopped_breakpoint():
    r = parse_mi_line('*stopped,reason="breakpoint-hit",thread-id="1"')
    assert r["kind"] == "async" and r["class"] == "stopped"
    assert r["fields"]["reason"] == "breakpoint-hit"

def test_entry_point_hit():
    r = parse_mi_line('*stopped,reason="entry-point-hit"')
    assert r["fields"]["reason"] == "entry-point-hit"

def test_var_create_result():
    r = parse_mi_line('^done,name="a",value="0",type="int"')
    assert r["kind"] == "result" and r["class"] == "done"
    assert r["fields"]["value"] == "0"

def test_error_result():
    assert parse_mi_line('^error,msg="oops"')["class"] == "error"

def test_non_mi_returns_stream():
    assert parse_mi_line("random console text")["kind"] == "stream"
```

- [ ] **Step 2: Run, verify fail** -> no module `miparse`.
- [ ] **Step 3: Implement `miparse.py`** - classify by leading token (`^`/`*`/`=`/`~`/`@`/`&`/`(gdb)`), then extract top-level `key="value"` and `key=value` pairs with a small scanner that respects `"`, `{}`, `[]` nesting. Keep to the fields the backend needs (`reason`, `name`, `value`, `type`, `msg`, `bkpt`). Unrecognized lines -> `{"kind":"stream","class":"console","fields":{"text":line}}`.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** - `git add scripts/dbgsession/miparse.py scripts/dbgsession/test_miparse.py && git commit -m "feat(driver): hand-rolled GDB/MI mini-parser"`

### Task 1.4: Backend base + MiBackend (netcoredbg + gdb)

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/backends/__init__.py`, `backends/base.py`, `backends/mi.py`
- Test: `using-a-debugger/scripts/dbgsession/test_mi_backend.py` (integration; local-run, skipif tools absent)

**Interfaces:**
- Produces: `class Backend` (ABC) with the **uniform verb methods** every backend implements:
  `start()`, `set_breakpoint(file, line) -> str`, `run() -> str`, `cont() -> str`, `step_over() -> str`, `step_into() -> str`, `read_local(name) -> str`, `backtrace() -> str`, `raw(native_cmd) -> str`, `stop()`.
- `MiBackend(debugger, kind, program, program_args, debugger_path)` where `debugger in {"netcoredbg","gdb"}`. Uses pipe for netcoredbg, pty for gdb-on-POSIX. Consumed by the server's verb dispatch (Task 1.8).

**Verified behavior (spike note - copy constants exactly):**
- netcoredbg launch: `<netcoredbg> --interpreter=mi -- dotnet <app.dll>`; gdb launch: `gdb --interpreter=mi2 --args <prog> <args...>`.
- Breakpoint: `-break-insert <file>:<line>`. Run: `-exec-run`. Continue: `-exec-continue`. Step over: `-exec-next`. Step into: `-exec-step`.
- Stop = read transport until a parsed `*stopped` record appears, then drain to the next `(gdb)` prompt. Return a human-readable stop summary.
- netcoredbg only: after `-exec-run`, the FIRST `*stopped` is `reason="entry-point-hit"` - the backend must auto-`-exec-continue` once to reach the user breakpoint (do NOT do this for gdb).
- Local read: `-var-create <name> * <name>` -> parse `value="..."` from the `^done`. (`-stack-list-locals` / `-data-evaluate-expression` are NOT in netcoredbg's MI subset - do not use them.)

- [ ] **Step 1: Write the failing integration test** (`test_mi_backend.py`)

```python
import os, shutil, subprocess, sys, tempfile, textwrap, pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends.mi import MiBackend

NETCOREDBG = shutil.which("netcoredbg") or os.environ.get("NETCOREDBG")

@pytest.mark.skipif(not NETCOREDBG or not shutil.which("dotnet"),
                    reason="needs netcoredbg + dotnet")
def test_netcoredbg_live_session_reads_locals():
    d = Path(tempfile.mkdtemp())
    subprocess.run(["dotnet", "new", "console", "-o", str(d)], check=True)
    (d / "Program.cs").write_text(textwrap.dedent('''
        int Add(int a, int b){ int sum=a+b; return sum; }   // line 2
        for (int i=0;i<3;i++){ int r=Add(i,i*2); System.Console.WriteLine(r); }
    '''))
    subprocess.run(["dotnet", "build", "-c", "Debug"], cwd=d, check=True)
    dll = next(d.glob("bin/Debug/net*/*.dll"))
    b = MiBackend("netcoredbg", "pipe", "dotnet", [str(dll)], NETCOREDBG)
    b.start()
    try:
        b.set_breakpoint("Program.cs", 2)
        b.run()                      # auto-skips entry-point-hit to the user bp
        assert b.read_local("a") == "0"
        assert b.read_local("b") == "0"
        b.cont()                     # next hit
        assert b.read_local("a") == "1"
    finally:
        b.stop()
```

(A sibling `test_gdb_backend.py` guarded by `shutil.which("gdb")` mirrors this against a `g++ -g -O0` C++ target with `MiBackend("gdb","pty",...)` - runs on Linux/llamabox.)

- [ ] **Step 2: Run, verify fail** -> no `backends.mi`.
- [ ] **Step 3: Implement `base.py` + `mi.py`** per the verified behavior above, using `Transport` (Task 1.2) and `parse_mi_line` (Task 1.3). Gate stop on a parsed `*stopped`; implement the netcoredbg entry-point skip; translate verbs to MI commands; extract `value` for `read_local`.
- [ ] **Step 4: Run, verify pass** (with netcoredbg present locally; gdb leg on llamabox).
- [ ] **Step 5: Commit** - `git add scripts/dbgsession/backends/__init__.py scripts/dbgsession/backends/base.py scripts/dbgsession/backends/mi.py scripts/dbgsession/test_mi_backend.py && git commit -m "feat(driver): Backend base + MI backend (netcoredbg + gdb)"`

### Task 1.5: LldbCliBackend

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/backends/lldb_cli.py`
- Test: `using-a-debugger/scripts/dbgsession/test_lldb_backend.py` (integration; skipif no working lldb)

**Verified behavior (spike note):**
- Launch (pipe): `<lldb> --no-use-colors <program> -- <args>`. Marker: `script print("TOKEN")`.
- Execution verbs (`run`/`continue`/`step`) race the marker (async stop on a background thread). For those: send the command, `read_until` matches `re.compile(r"stop reason =|Process \d+ exited|exited with status")`, THEN send the marker and drain to it. For synchronous verbs (`breakpoint set`, `frame variable`) the marker can follow immediately.
- Local read: `frame variable <name>` -> parse the value after `=`.
- Quit: send `process kill` then `quit` (bare `quit` while stopped hangs); or `transport.close()` (kills).
- Binary: do NOT trust `lldb` on PATH (Windows system LLVM lldb crashes - missing python311.dll). Resolve via `find_debugger("lldb")` (Task 1.7).

- [ ] **Step 1: Write the failing integration test** (`test_lldb_backend.py`)

```python
import os, shutil, subprocess, sys, tempfile, pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends.lldb_cli import LldbCliBackend
from discovery import find_debugger

LLDB = find_debugger("lldb")  # working binary or None

@pytest.mark.skipif(not LLDB or not shutil.which("clang++"), reason="needs working lldb + clang++")
def test_lldb_live_session_reads_locals():
    d = Path(tempfile.mkdtemp())
    (d / "hello.cpp").write_text("int add(int a,int b){int s=a+b;return s;}\nint main(){return add(2,5)-7;}\n")
    exe = d / ("hello.exe" if os.name == "nt" else "hello")
    subprocess.run(["clang++", "-g", "-O0", "-o", str(exe), str(d / "hello.cpp")], check=True)
    b = LldbCliBackend("lldb", "pipe", str(exe), [], LLDB)
    b.start()
    try:
        b.set_breakpoint("hello.cpp", 1)
        out = b.run()
        assert "stop reason" in out.lower()
        assert b.read_local("a") == "2"
        assert b.read_local("b") == "5"
    finally:
        b.stop()
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `lldb_cli.py`** subclassing `Backend`, using the content-gating algorithm above for execution verbs and immediate-marker for synchronous ones.
- [ ] **Step 4: Run, verify pass** (uses the discovered CLion-bundled lldb on chonkers).
- [ ] **Step 5: Commit** - `git add scripts/dbgsession/backends/lldb_cli.py scripts/dbgsession/test_lldb_backend.py && git commit -m "feat(driver): lldb CLI backend (content-gated)"`

### Task 1.6: Install cdb + CdbBackend

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/backends/cdb.py`
- Test: `using-a-debugger/scripts/dbgsession/test_cdb_backend.py` (integration; Windows; skipif no cdb)

- [ ] **Step 1: Install cdb (one-time machine setup, Windows)**

cdb is absent. Install the Windows SDK "Debugging Tools for Windows" so `cdb.exe` exists under `%ProgramFiles(x86)%\Windows Kits\10\Debuggers\x64\`. Research the least-invasive method first (e.g. `winget install --id Microsoft.WinDbg` provides WinDbgX but NOT classic `cdb.exe`; the classic console `cdb.exe` ships with the SDK Debugging Tools feature - the standalone SDK installer with only that feature selected, or `winget install Microsoft.WindowsSDK.*` plus the Debugging Tools component). Confirm `cdb -version`. Record the exact method used in the spike note so `tooling-setup.md` (Task 2.3) documents it.

- [ ] **Step 2: Write the failing integration test** (`test_cdb_backend.py`)

```python
import os, shutil, subprocess, sys, tempfile, pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends.cdb import CdbBackend
from discovery import find_debugger

CDB = find_debugger("cdb")

@pytest.mark.skipif(not CDB or os.name != "nt" or not shutil.which("clang++"),
                    reason="needs cdb + clang++ on Windows")
def test_cdb_live_session_breaks_on_function():
    d = Path(tempfile.mkdtemp())
    (d / "hello.cpp").write_text("int add(int a,int b){int s=a+b;return s;}\nint main(){return add(2,5)-7;}\n")
    exe = d / "hello.exe"
    subprocess.run(["clang++", "-g", "-gcodeview", "-O0", "-o", str(exe), str(d / "hello.cpp")], check=True)
    b = CdbBackend("cdb", "pipe", str(exe), [], CDB)
    b.start()
    try:
        b.set_breakpoint("hello.cpp", 1)   # translates to a bp on file:line
        out = b.run()                      # g
        assert "add" in out.lower() or "breakpoint" in out.lower()
    finally:
        b.stop()
```

- [ ] **Step 3: Verify fail.**
- [ ] **Step 4: Implement `cdb.py`** - native command translation: `set_breakpoint` -> a `bp` on `` `file:line` ``; `run`/`cont` -> `g`; `step_over` -> `p`; `step_into` -> `t`; `read_local` -> `dv <name>` (parse `name = value`); `backtrace` -> `k`; marker `.echo TOKEN`; prompt is `N:NNN> ` (e.g. `0:000> `). cdb is synchronous; the marker follows the command. Quit: `q`.
- [ ] **Step 5: Verify pass.**
- [ ] **Step 6: Commit** - `git add scripts/dbgsession/backends/cdb.py scripts/dbgsession/test_cdb_backend.py && git commit -m "feat(driver): cdb backend (Windows native)"`

### Task 1.7: Debugger binary discovery

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/discovery.py`
- Test: `using-a-debugger/scripts/dbgsession/test_discovery.py`

**Interfaces:**
- Produces: `find_debugger(kind: str) -> str | None` for `kind in {"netcoredbg","gdb","lldb","cdb"}`. Returns an invocable path or None. NO hard-coded user paths - derive from `PATH`, env overrides (`NETCOREDBG`, `LLDB`, `CDB`), and platform install roots via env (`%ProgramFiles%`, `%LOCALAPPDATA%`, `%ProgramFiles(x86)%`). Consumed by the backends and the CLI.

**Spike facts to encode:**
- lldb: a `lldb` on PATH may be broken (Windows LLVM missing python311.dll). `find_debugger("lldb")` must run `<lldb> --version` and reject a non-zero/crashing exit, then fall back to a CLion-bundled lldb discovered under `%LOCALAPPDATA%\Programs\CLion\bin\lldb\win\x64\bin\lldb.exe` (glob, do not hard-code the user).
- cdb: PATH, then `%ProgramFiles(x86)%\Windows Kits\10\Debuggers\x64\cdb.exe`.
- netcoredbg: PATH, then `$NETCOREDBG`.

- [ ] **Step 1: Write tests** - `test_discovery.py`: `find_debugger("gdb")` returns `shutil.which("gdb")` when present; an unknown kind raises; the lldb health-check rejects a stub that exits non-zero (monkeypatch a fake `lldb` script). Platform-guard the tests.
- [ ] **Step 2: Verify fail.**
- [ ] **Step 3: Implement `discovery.py`** with the health-check + fallbacks above.
- [ ] **Step 4: Verify pass.**
- [ ] **Step 5: Commit** - `git add scripts/dbgsession/discovery.py scripts/dbgsession/test_discovery.py && git commit -m "feat(driver): working-binary discovery (lldb health-check, cdb/netcoredbg fallbacks)"`

### Task 1.8: Server + client + CLI (uniform verbs over a socket)

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/server.py`, `client.py`, `using-a-debugger/scripts/dbg-session.py`
- Test: `using-a-debugger/scripts/dbgsession/test_cli_e2e.py` (integration; skipif no debugger)

**Interfaces:**
- `Server(backend)` owns one Backend, listens on `127.0.0.1:0`, writes `<session_dir>/port`, and dispatches a one-line **verb** request to the backend method, returning its text. Verbs: `break FILE:LINE`, `run`, `continue`, `step`, `stepin`, `local NAME`, `bt`, `raw NATIVE...`, and `__STOP__`.
- CLI: `dbg-session.py start --debugger {netcoredbg,gdb,lldb,cdb} [--kind pipe|pty] --session NAME -- PROGRAM [ARGS...]` (resolves the binary via `find_debugger`, builds the right Backend, daemonizes the server); `dbg-session.py send --session NAME "VERB ..."`; `dbg-session.py stop --session NAME`.
- Session state under `tempfile.gettempdir()/dbg-session/<name>`.

- [ ] **Step 1: Write the failing e2e test** (`test_cli_e2e.py`) - start a netcoredbg (or lldb) session via the CLI, `send break ...`, `send run`, `send local a`, assert the value, `stop`. Mirror the Task 1.4/1.5 setup but drive through `subprocess` calls to `dbg-session.py` (each `send` a separate process - proving state persists in the server).
- [ ] **Step 2: Verify fail.**
- [ ] **Step 3: Implement `server.py`** (verb -> backend dispatch + socket loop; daemonize by re-exec with `_DBG_SERVER=1`, detached, write the port file, `find_debugger` + build Backend by `--debugger`), `client.py` (read port file with retry, send verb, print reply), `dbg-session.py` (argparse start/send/stop; map `--debugger` to backend class + default transport: netcoredbg=pipe, gdb=pty on POSIX, lldb=pipe, cdb=pipe).
- [ ] **Step 4: Verify pass.**
- [ ] **Step 5: Commit** - `git add scripts/dbgsession/server.py scripts/dbgsession/client.py scripts/dbg-session.py scripts/dbgsession/test_cli_e2e.py && git commit -m "feat(driver): server + client + dbg-session CLI (uniform verbs)"`

## Phase 2: Reference content + orchestrator

Every command in these references is copied from a session actually run during the spike or while authoring (run it, paste real output shape). No invented flags.

### Task 2.1: Interaction-mode references

**Files:**
- Create: `using-a-debugger/references/scripted-batch.md`, `using-a-debugger/references/interactive-sessions.md`

- [ ] **Step 1: Author `scripted-batch.md`**

Content (concrete, verified): the non-interactive invocation per debugger, each with a runnable example against the `hello` target:
- lldb: `lldb -b -o "breakpoint set -f hello.cpp -l 3" -o run -o "frame variable" -o continue -- ./hello` (and the `-s scriptfile` form).
- gdb: `gdb -batch -ex "break hello.cpp:3" -ex run -ex "info locals" -ex continue --args ./hello`.
- cdb: `cdb -cf script.txt ./hello.exe` with a `script.txt` example (`bp`, `g`, `dv`, `q`).
- netcoredbg: `netcoredbg --interpreter=cli --command=script.txt -- dotnet App.dll` (marker/exit confirmed in spike).
When to use: known breakpoint location, want a reproducible one-shot capture, or in CI. Section "reading the output" shows what a stop/locals dump looks like.

- [ ] **Step 2: Author `interactive-sessions.md`**

Content: how to use `scripts/dbg-session.py` for live exploration, with a worked transcript (start, set breakpoint, run, `frame variable`, `step`, re-read, `expression` to mutate, `continue`, stop). Explain the model (server holds the debuggee; each `send` is one tool call). Document `--session` for multiple concurrent sessions, the temp-dir state location, and recovery (`stop` then re-`start` if a session wedges). State the escalation rule: start scripted; escalate to a live session when you do not yet know where the bug is or must follow state interactively. Cross-link the spike note's gotchas (colors, buffering) as the troubleshooting section.

- [ ] **Step 3: Commit**
```bash
git add using-a-debugger/references/scripted-batch.md using-a-debugger/references/interactive-sessions.md
git commit -m "docs(refs): scripted-batch + interactive-sessions"
```

### Task 2.2: Per-debugger references

**Files:**
- Create: `using-a-debugger/references/lldb-native.md`, `gdb-native.md`, `cdb-windows.md`, `netcoredbg-dotnet.md` (all under `references/`)

- [ ] **Step 1: Author the four per-debugger references**

Each follows the same skeleton so the orchestrator can point at any one:
- **When this debugger** (platform + language + build-info fit: lldb = macOS/Linux/Windows-clang native; gdb = Linux native; cdb = Windows/MSVC-PDB native; netcoredbg = .NET managed, all platforms).
- **Get the debug build** (lldb/gdb: `-g -O0`; cdb: ensure PDB next to the binary; netcoredbg: `dotnet build -c Debug`, portable PDBs).
- **Core command cheatsheet** mapped to the universal verbs the orchestrator names (set breakpoint, run, continue, step over/in/out, backtrace, read locals, read a memory expression, evaluate/mutate). Real per-debugger syntax, verified.
- **Driver/adapter note**: the `dbg-session.py --debugger <name>` value and the marker convention from the spike note.
- **Gotchas** observed in the spike (e.g. lldb color codes, cdb symbol path `_NT_SYMBOL_PATH`, netcoredbg CLI vs MI).

- [ ] **Step 2: Commit**
```bash
git add using-a-debugger/references/lldb-native.md using-a-debugger/references/gdb-native.md using-a-debugger/references/cdb-windows.md using-a-debugger/references/netcoredbg-dotnet.md
git commit -m "docs(refs): per-debugger cheatsheets (lldb/gdb/cdb/netcoredbg)"
```

### Task 2.3: Tooling-setup reference

**Files:**
- Create: `using-a-debugger/references/tooling-setup.md`

- [ ] **Step 1: Author `tooling-setup.md`**

Content: a detect-then-install playbook with NO hard-coded machine paths.
- **Detect**: check `PATH` (`command -v` / `where`), plus known install roots discovered via env (`%ProgramFiles%`, LLVM under it; Windows SDK Debuggers under `%ProgramFiles(x86)%\Windows Kits\10\Debuggers`). Show the cross-platform probe.
- **Install per platform**: netcoredbg release artifact (GitHub releases, extract, add to PATH); cdb via the Windows SDK "Debugging Tools for Windows" feature; lldb/gdb via `apt`/`brew`/winget or the LLVM installer. Each as copyable commands, parameterized.
- **Pick the right tool** quick-table (language x platform -> debugger), mirroring SKILL.md's matrix.

- [ ] **Step 2: Commit**
```bash
git add using-a-debugger/references/tooling-setup.md
git commit -m "docs(refs): cross-platform tooling-setup playbook"
```

### Task 2.4: SKILL.md orchestrator body

**Files:**
- Modify: `using-a-debugger/SKILL.md`

- [ ] **Step 1: Write the orchestrator body**

Sections:
1. **When to use / when not** - use when a bug resists print-debugging or you must inspect live state; not for trivial bugs a log line settles, not a replacement for `systematic-debugging` (this is the *tooling* arm; cross-link it as the *process*).
2. **The loop**: form a hypothesis (via systematic-debugging) -> pick a breakpoint that would confirm/refute it -> set it -> run -> read state -> step -> conclude. Debugger serves the hypothesis; do not aimlessly step.
3. **Mode decision**: scripted first (-> `references/scripted-batch.md`); escalate to a live session for exploration (-> `references/interactive-sessions.md`).
4. **Debugger selection matrix** (language x platform x build-info -> reference). Points at the per-debugger files and `tooling-setup.md` for "not installed."
5. **Mixed-mode pointer** -> `references/mixed-mode.md` (Phase 3).
6. **The driver** one-liner: `scripts/dbg-session.py start|send|stop`.
Keep it short and navigational; weeds live in references. Follow `superpowers:writing-skills` for tone/length.

- [ ] **Step 2: Validate the skill structurally**

Run: `cd using-a-debugger && agentskills validate .` (or the skills-dev `scripts/validate_skills.py` path once it is a submodule)
Expected: PASS (valid frontmatter, no local-only path references, not vacuous).

- [ ] **Step 3: Commit**
```bash
git add using-a-debugger/SKILL.md
git commit -m "docs(skill): orchestrator body - mode + debugger selection"
```

---

## Phase 3: Mixed-mode, evals, docs

### Task 3.1: Mixed-mode reference (shape decided by Phase 0 verdict)

**Files:**
- Create: `using-a-debugger/references/mixed-mode.md`

- [ ] **Step 1: Author per the Phase 0 verdict**

- If a toolset reliably crosses the C#/native boundary: a **fully-worked file-wizard flow** (build both halves per `AGENTS.md`; set a managed breakpoint in the P/Invoke caller; set a native breakpoint on the export in `MFTLibNative.dll`; show stepping from managed into native with both frame sets), naming the exact toolset.
- Otherwise: an **honest-limits reference** - per platform/toolset what is and is not possible, plus the realistic workarounds (two debuggers attached to one process: netcoredbg for managed + cdb/lldb for native; or break-on-native-entry from the native side while the managed side runs; or VS for true mixed-mode). Cite the spike evidence.
Mark any macOS path `(unverified on macOS)`.

- [ ] **Step 2: Commit**
```bash
git add using-a-debugger/references/mixed-mode.md
git commit -m "docs(refs): mixed-mode managed/native (per spike verdict)"
```

### Task 3.2: Evals

**Files:**
- Create: `using-a-debugger/evals/evals.json`, `using-a-debugger/evals/run.py`, `using-a-debugger/evals/grade.py`, `using-a-debugger/workspace/` mock targets

- [ ] **Step 1: Adapt run.py / grade.py from fast-tests**

Copy `fast-tests/evals/run.py` and `grade.py`, change `skill_name` to `using-a-debugger` and the `SKILL_SECTION_WRAPPER` header. Keep the single-turn harness and the `Read,Grep,Glob` tool restriction.

- [ ] **Step 2: Author `evals.json` scenarios**

Cover the decision surface (mirror the fast-tests bucket style):
- decision: "wrong value, cannot localize" -> proposes a breakpoint + reading state, not more prints.
- mode: known location/CI -> scripted/batch; exploratory -> live session.
- selection: a Linux C++ segfault -> gdb/lldb; a .NET `NullReferenceException` -> netcoredbg; a Windows MSVC crash with a PDB -> cdb.
- tooling: "debugger not installed" -> detect-then-install, not give up.
- mixed-mode: C# P/Invoke into native -> the Phase-3 verdict's guidance (worked flow or honest limits), never a false promise.
- false-positive guard: a one-line obvious bug -> does NOT reach for the debugger.
Include the universal `no_hallucinated_claims` assertion.

- [ ] **Step 3: Smoke-run the evals (with vs without skill) on a couple scenarios**

Run: `python using-a-debugger/evals/run.py --evals using-a-debugger/evals/evals.json --skill-md using-a-debugger/SKILL.md --output-dir using-a-debugger/workspace/eval-out --only-eval 0`
Expected: produces `response.md`; the with_skill response proposes a debugger workflow. (Full grading optional; the harness running is the gate.)

- [ ] **Step 4: Commit**
```bash
git add using-a-debugger/evals/
git commit -m "test(evals): using-a-debugger decision-surface scenarios"
```

### Task 3.3: README + documentation pass

**Files:**
- Create: `using-a-debugger/README.md` (dev-facing)
- Modify: skills-dev `README.md` skill list if it enumerates skills

- [ ] **Step 1: Write README.md** (what the skill is, how to run the driver locally, how to run evals, the per-debugger support matrix, the mixed-mode verdict).

- [ ] **Step 2: Run the docs-update check** across skills-dev `README.md` / `CLAUDE.md` for anything that enumerates skills; add `using-a-debugger` where the fleet lists skills. Bring any drifted line in sync.

- [ ] **Step 3: Commit**
```bash
git add using-a-debugger/README.md README.md
git commit -m "docs: using-a-debugger README + skill-list update"
```

---

## Phase 4: Repo creation + submodule wiring + install

Follow skills-dev `CLAUDE.md` "Adding a new skill" exactly. Use the schoen admin token (`~/.gitea-token`) for repo creation under `schoen`, default Matt Schoen git identity for commits.

### Task 4.1: Create remote repos

- [ ] **Step 1: Create Gitea + GitHub repos**
```bash
# Gitea (public; needed so umbrella CI's recursive checkout can clone anonymously)
curl -s -H "Authorization: token $(cat ~/.gitea-token)" -H "Content-Type: application/json" \
  -X POST https://gitea.llamabox.sticktoitive.net/api/v1/user/repos \
  -d '{"name":"skills-using-a-debugger","private":false,"auto_init":false}'
# Enable Actions if the repo will run CI:
curl -s -H "Authorization: token $(cat ~/.gitea-token)" -X PATCH \
  https://gitea.llamabox.sticktoitive.net/api/v1/repos/schoen/skills-using-a-debugger \
  -H "Content-Type: application/json" -d '{"has_actions":true}'
# GitHub
gh repo create mtschoen/skills-using-a-debugger --public
```
Expected: both repos exist, empty.

### Task 4.2: Init local dir, push, convert to submodule

- [ ] **Step 1: Push the existing skill repo to Gitea + GitHub**

The repo was initialized at Task 1.1 and already holds the full Phase 1-3 TDD history. Do NOT re-init or squash; push that history.
```bash
cd using-a-debugger
git remote add origin gitea@llamabox.sticktoitive.net:schoen/skills-using-a-debugger.git
git push -u origin main
git remote add github git@github.com:mtschoen/skills-using-a-debugger.git
git push github main   # no -u; upstream stays origin/main
cd ..
```

- [ ] **Step 2: Remove the local dir and re-add as a submodule** (Windows: `cd ..` first to avoid "Device or resource busy")
```bash
rm -rf using-a-debugger
git submodule add gitea@llamabox.sticktoitive.net:schoen/skills-using-a-debugger.git using-a-debugger
git config -f .gitmodules submodule.using-a-debugger.url ../skills-using-a-debugger.git
git -C using-a-debugger remote add github git@github.com:mtschoen/skills-using-a-debugger.git
# do NOT run `git submodule sync`
```

- [ ] **Step 3: Add the submodule to the umbrella ruff exclude** (skills-dev `pyproject.toml` `[tool.ruff] exclude`), since the driver Python lives in the submodule.

- [ ] **Step 4: Commit the submodule pointer**
```bash
git add .gitmodules using-a-debugger pyproject.toml
git commit -m "feat(skills): add using-a-debugger submodule"
```

### Task 4.3: Verify install + push everything

- [ ] **Step 1: Dry-run the installer**

Run: `./install-skills.sh -n using-a-debugger`
Expected: `install using-a-debugger -> ~/.claude/skills/using-a-debugger` (one line for a fresh install).

- [ ] **Step 2: Real install + smoke the deployed skill**

Run: `./install-skills.sh using-a-debugger` then confirm `~/.claude/skills/using-a-debugger/SKILL.md` and `scripts/dbg-session.py` exist, and `evals/` did NOT ship (allowlist).

- [ ] **Step 3: Push all hosts**

Run: `scripts/push-all.sh`
Expected: submodule + umbrella pushed to origin (Gitea) and github, no non-FF skips.

- [ ] **Step 4: Final verification** - in a fresh session, confirm the skill is discoverable (appears in the skills list) and `dbg-session.py start/send/stop` drives a live lldb session end-to-end against `hello.cpp`.

---

## Branch-finish (after all phases)

Fold durable insight into real docs before deleting this plan:
- The persistent-session driver design (client/server + marker delimiting) -> `using-a-debugger/README.md` "Architecture" + inline module docstrings (already present).
- The mixed-mode verdict + per-toolset capability table -> `references/mixed-mode.md` (already its home).
- Cross-machine debugger availability + any install gotchas -> the spike note stays in `~/.claude/notes/` as the durable reference.
Then delete this plan file; `git log` is the audit trail.
