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

Author content in a local `using-a-debugger/` directory inside skills-dev, made into **its own git repo at Task 1.1** (the submodule conversion in Phase 4 pushes this history to Gitea/GitHub and re-adds it as a submodule; it does NOT re-init). **Working-directory convention for Phases 1-3:** all `git add`/`git commit` commands below run from **inside the `using-a-debugger/` repo**, with paths relative to it (drop the leading `using-a-debugger/` shown for clarity). All driver code is stdlib-only Python. The code below assumes the Phase 0 verdict was `pipe+marker`; if Phase 0 chose `sb-api`, swap `server.py`'s backend per the spike note (the client/CLI/adapters are unchanged).

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

### Task 1.2: Per-debugger adapters

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/adapters.py`
- Test: `using-a-debugger/scripts/dbgsession/test_adapters.py`

**Interfaces:**
- Produces: `ADAPTERS: dict[str, Adapter]`; `Adapter` with fields `name`, `launch_argv(program, program_args) -> list[str]`, `marker_cmd(token) -> str`, `quit_cmd: str`. Consumed by `server.py`.

- [ ] **Step 1: Write the failing test**

`test_adapters.py`:
```python
from adapters import ADAPTERS

def test_lldb_marker_uses_script_print():
    a = ADAPTERS["lldb"]
    assert a.marker_cmd("TOK") == 'script print("TOK")'

def test_lldb_launch_argv_includes_program_and_args():
    a = ADAPTERS["lldb"]
    argv = a.launch_argv("/tmp/hello", ["--flag"])
    assert argv[0] == "lldb"
    assert "/tmp/hello" in argv
    assert "--flag" in argv

def test_gdb_marker_uses_echo():
    assert ADAPTERS["gdb"].marker_cmd("TOK") == "echo TOK\\n"

def test_every_adapter_has_quit():
    assert all(a.quit_cmd for a in ADAPTERS.values())
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd using-a-debugger/scripts/dbgsession && python -m pytest test_adapters.py -q`
Expected: FAIL (`No module named 'adapters'`).

- [ ] **Step 3: Implement adapters.py**

```python
"""Per-debugger launch + marker conventions for the session server.

A debugger is driven over piped stdin/stdout. After each user command the
server sends marker_cmd(token), which forces the debugger to echo a unique
delimiter line so the server knows where that command's output ends.

Marker conventions and MI/CLI choices are grounded in the spike note
~/.claude/notes/spike_debugger_sessions.md.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Adapter:
    name: str
    launch_argv: Callable[[str, list], list]
    marker_cmd: Callable[[str], str]
    quit_cmd: str


def _lldb_argv(program, program_args):
    return ["lldb", "--no-use-colors", program, "--", *program_args] if program_args \
        else ["lldb", "--no-use-colors", program]


def _gdb_argv(program, program_args):
    base = ["gdb", "--nx", "--quiet"]
    return [*base, "--args", program, *program_args] if program_args else [*base, program]


def _cdb_argv(program, program_args):
    return ["cdb", program, *program_args]


def _netcoredbg_argv(program, program_args):
    # program is the managed entry: e.g. "dotnet" with app.dll in program_args,
    # or a published host exe. Confirmed against the spike note.
    return ["netcoredbg", "--interpreter=cli", "--", program, *program_args]


ADAPTERS = {
    "lldb": Adapter("lldb", _lldb_argv, lambda t: f'script print("{t}")', "quit"),
    "gdb": Adapter("gdb", _gdb_argv, lambda t: f"echo {t}\\n", "quit"),
    "cdb": Adapter("cdb", _cdb_argv, lambda t: f".echo {t}", "q"),
    "netcoredbg": Adapter("netcoredbg", _netcoredbg_argv, lambda t: f'print "{t}"', "quit"),
}
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest test_adapters.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**
```bash
git add using-a-debugger/scripts/dbgsession/adapters.py using-a-debugger/scripts/dbgsession/test_adapters.py
git commit -m "feat(driver): per-debugger launch + marker adapters"
```

### Task 1.3: Session server (owns the debugger, marker-delimited reads)

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/server.py`
- Test: `using-a-debugger/scripts/dbgsession/test_server_lldb.py` (integration; local-run, skipped if lldb/clang absent)

**Interfaces:**
- Produces: `Server(debugger, program, program_args, session_dir)`, methods `start()`, `send(command: str) -> str`, `stop()`. Writes `<session_dir>/port` (int) on start. Consumed by `dbg-session.py` and `client.py`.

- [ ] **Step 1: Write the failing integration test**

`test_server_lldb.py` (the real verify - drives a live lldb session across send() calls):
```python
import os, shutil, subprocess, tempfile, textwrap, pytest
from pathlib import Path
from server import Server

HELLO = textwrap.dedent('''
    int add(int a,int b){int s=a+b;return s;}
    int main(){int r=add(2,5);return r-r;}
''')

@pytest.mark.skipif(not shutil.which("lldb") or not shutil.which("clang++"),
                    reason="needs lldb + clang++")
def test_live_lldb_session_holds_state_across_sends():
    d = Path(tempfile.mkdtemp())
    (d / "hello.cpp").write_text(HELLO)
    exe = d / ("hello.exe" if os.name == "nt" else "hello")
    subprocess.run(["clang++", "-g", "-O0", "-o", str(exe), str(d / "hello.cpp")], check=True)
    s = Server("lldb", str(exe), [], d)
    s.start()
    try:
        assert (d / "port").exists()
        s.send("breakpoint set --file hello.cpp --line 1")
        out_run = s.send("run")
        assert "stop reason" in out_run.lower()
        out_vars = s.send("frame variable a b")
        assert "a =" in out_vars and "b =" in out_vars   # state is live at the hit
    finally:
        s.stop()
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd using-a-debugger/scripts/dbgsession && python -m pytest test_server_lldb.py -q`
Expected: FAIL (`No module named 'server'`).

- [ ] **Step 3: Implement server.py**

```python
"""Long-lived server that owns one debugger subprocess and answers send()
calls with marker-delimited command output. A short-lived client (one per
agent tool call) talks to it over a localhost socket so the debuggee's state
survives between calls.

Backend grounded in the spike note. If the spike chose the lldb SB API over
piped stdin, replace _spawn/_read_until_marker with the SB-API variant
documented there; the socket protocol below is unchanged.
"""
import itertools
import queue
import socket
import subprocess
import threading
from pathlib import Path

from adapters import ADAPTERS


class Server:
    def __init__(self, debugger, program, program_args, session_dir):
        self.adapter = ADAPTERS[debugger]
        self.program = program
        self.program_args = list(program_args)
        self.session_dir = Path(session_dir)
        self._proc = None
        self._lines = queue.Queue()
        self._tokens = itertools.count(1)
        self._sock = None
        self._serving = False

    def start(self):
        self._proc = subprocess.Popen(
            self.adapter.launch_argv(self.program, self.program_args),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        port = self._sock.getsockname()[1]
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "port").write_text(str(port))

    def _pump(self):
        for line in self._proc.stdout:
            self._lines.put(line)

    def send(self, command, timeout=30):
        token = f"@@DBG{next(self._tokens)}@@"
        self._proc.stdin.write(command + "\n")
        self._proc.stdin.write(self.adapter.marker_cmd(token) + "\n")
        self._proc.stdin.flush()
        out = []
        while True:
            line = self._lines.get(timeout=timeout)
            if line.strip() == token:
                return "".join(out)
            out.append(line)

    def serve_forever(self):
        self._serving = True
        while self._serving:
            conn, _ = self._sock.accept()
            with conn:
                data = conn.recv(65536).decode("utf-8")
                if data == "__STOP__":
                    self._serving = False
                    reply = "stopped"
                else:
                    try:
                        reply = self.send(data)
                    except queue.Empty:
                        reply = "__TIMEOUT__"
                conn.sendall(reply.encode("utf-8"))
        self.stop()

    def stop(self):
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.stdin.write(self.adapter.quit_cmd + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
        except Exception:
            if self._proc:
                self._proc.kill()
        finally:
            if self._sock:
                self._sock.close()
            p = self.session_dir / "port"
            if p.exists():
                p.unlink()
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest test_server_lldb.py -q`
Expected: PASS (1 passed) on a machine with lldb + clang++. If skipped, run on a machine that has them (chonkers has lldb; install clang if needed) before checking the box.

- [ ] **Step 5: Commit**
```bash
git add using-a-debugger/scripts/dbgsession/server.py using-a-debugger/scripts/dbgsession/test_server_lldb.py
git commit -m "feat(driver): session server with marker-delimited reads"
```

### Task 1.4: Client + CLI entry point

**Files:**
- Create: `using-a-debugger/scripts/dbgsession/client.py`, `using-a-debugger/scripts/dbg-session.py`
- Test: `using-a-debugger/scripts/dbgsession/test_cli_lldb.py` (integration, local-run)

**Interfaces:**
- Consumes: `Server` (Task 1.3).
- Produces CLI: `dbg-session.py start --debugger D --session NAME -- PROGRAM [ARGS...]` (forks the server, backgrounded); `dbg-session.py send --session NAME "COMMAND"` (prints output); `dbg-session.py stop --session NAME`.

- [ ] **Step 1: Write the failing end-to-end CLI test**

`test_cli_lldb.py`:
```python
import os, shutil, subprocess, sys, tempfile, textwrap, time, pytest
from pathlib import Path

CLI = str(Path(__file__).resolve().parents[1] / "dbg-session.py")
HELLO = "int add(int a,int b){int s=a+b;return s;}\nint main(){return add(2,5)-7;}\n"

@pytest.mark.skipif(not shutil.which("lldb") or not shutil.which("clang++"),
                    reason="needs lldb + clang++")
def test_cli_start_send_stop():
    d = Path(tempfile.mkdtemp())
    (d / "hello.cpp").write_text(HELLO)
    exe = d / ("hello.exe" if os.name == "nt" else "hello")
    subprocess.run(["clang++", "-g", "-O0", "-o", str(exe), str(d / "hello.cpp")], check=True)
    name = "test"
    subprocess.run([sys.executable, CLI, "start", "--debugger", "lldb",
                    "--session", name, "--", str(exe)], check=True, cwd=d)
    try:
        subprocess.run([sys.executable, CLI, "send", "--session", name,
                        "breakpoint set --file hello.cpp --line 1"], check=True, cwd=d)
        run = subprocess.run([sys.executable, CLI, "send", "--session", name, "run"],
                             check=True, cwd=d, capture_output=True, text=True)
        assert "stop reason" in run.stdout.lower()
    finally:
        subprocess.run([sys.executable, CLI, "stop", "--session", name], cwd=d)
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd using-a-debugger/scripts/dbgsession && python -m pytest test_cli_lldb.py -q`
Expected: FAIL (CLI not found / no such command).

- [ ] **Step 3: Implement client.py**

```python
"""Short-lived client: read the session's port file, send one command, print
the reply. Each agent tool call is one client invocation; the debuggee stays
alive in the server."""
import socket
import time
from pathlib import Path


def _port(session_dir, retries=50):
    p = Path(session_dir) / "port"
    for _ in range(retries):
        if p.exists():
            return int(p.read_text())
        time.sleep(0.1)
    raise RuntimeError(f"no live session at {session_dir} (server not started?)")


def request(session_dir, message):
    with socket.create_connection(("127.0.0.1", _port(session_dir)), timeout=60) as s:
        s.sendall(message.encode("utf-8"))
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks).decode("utf-8")
```

- [ ] **Step 4: Implement dbg-session.py**

```python
#!/usr/bin/env python3
"""Drive a persistent debugger session across separate process invocations.

  dbg-session.py start --debugger lldb --session bug1 -- ./prog --flag
  dbg-session.py send  --session bug1 "breakpoint set --file x.cpp --line 42"
  dbg-session.py send  --session bug1 "run"
  dbg-session.py send  --session bug1 "frame variable"
  dbg-session.py stop  --session bug1

The server runs in the background holding the debuggee; send/stop are quick
clients. Session state lives under the OS temp dir keyed by --session.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "dbgsession"))
from client import request   # noqa: E402
from server import Server    # noqa: E402


def session_dir(name):
    return Path(tempfile.gettempdir()) / "dbg-session" / name


def cmd_start(args):
    d = session_dir(args.session)
    if (d / "port").exists():
        print(f"session '{args.session}' already running", file=sys.stderr)
        return 1
    # Daemonize: re-exec self as the server loop, detached.
    if os.environ.get("_DBG_SERVER") != "1":
        import subprocess
        env = {**os.environ, "_DBG_SERVER": "1"}
        kwargs = {"env": env, "cwd": os.getcwd()}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([sys.executable, __file__, *sys.argv[1:]], **kwargs)
        # Wait for the port file so callers can send immediately.
        from client import _port
        _port(d)
        print(f"started session '{args.session}' ({args.debugger})")
        return 0
    srv = Server(args.debugger, args.program, args.program_args, d)
    srv.start()
    srv.serve_forever()
    return 0


def cmd_send(args):
    print(request(session_dir(args.session), args.command), end="")
    return 0


def cmd_stop(args):
    try:
        print(request(session_dir(args.session), "__STOP__"))
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("--debugger", required=True)
    s.add_argument("--session", default="default")
    s.add_argument("program"); s.add_argument("program_args", nargs="*")
    s.set_defaults(func=cmd_start)
    se = sub.add_parser("send"); se.add_argument("--session", default="default")
    se.add_argument("command"); se.set_defaults(func=cmd_send)
    st = sub.add_parser("stop"); st.add_argument("--session", default="default")
    st.set_defaults(func=cmd_stop)
    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run, verify pass**

Run: `python -m pytest test_cli_lldb.py -q`
Expected: PASS (1 passed) where lldb + clang++ exist.

- [ ] **Step 6: Commit**
```bash
git add using-a-debugger/scripts/dbgsession/client.py using-a-debugger/scripts/dbg-session.py using-a-debugger/scripts/dbgsession/test_cli_lldb.py
git commit -m "feat(driver): client + dbg-session CLI (start/send/stop)"
```

---

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
