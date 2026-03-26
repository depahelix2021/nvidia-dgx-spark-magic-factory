#!/usr/bin/env python3
# ✨ NVIDIA DGX Spark Magic Factory
# Copyright 2026 Chris Morley / Lantern Light AI (https://www.lanternlight.ai)
# chris.morley@lanternlight.ai | depahelix@gmail.com
# Made with love in Massachusetts
#
# Need something like this built for you? I'm available for contracts & 100% remote work.
#
# ptr a0010001

import argparse
import hashlib
import io
import json
import logging
import os
import queue
import random
import re
import selectors
import subprocess
import sys
import textwrap
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, jsonify, request, Response
from dotenv import load_dotenv

load_dotenv()

# ptr a0010002

BASE = Path(__file__).parent
DATA = BASE / "data"
LOGS_DIR = DATA / "logs"
BUILDS_DIR = DATA / "builds"
RESEARCH_DIR = DATA / "research"
TIMINGS_FILE = DATA / "step_timings.json"
for d in [LOGS_DIR, BUILDS_DIR, RESEARCH_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def _load_timings() -> dict:
    if TIMINGS_FILE.exists():
        try:
            return json.loads(TIMINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_timing(step_id: str, duration: float):
    # ptr a0010003
    t = _load_timings()
    if step_id not in t:
        t[step_id] = []
    t[step_id].append(round(duration, 2))
    t[step_id] = t[step_id][-5:]
    TIMINGS_FILE.write_text(json.dumps(t, indent=2) + "\n")


def _estimate_duration(step_id: str) -> float | None:
    # ptr a0010003
    t = _load_timings()
    runs = t.get(step_id, [])
    return round(sum(runs) / len(runs), 1) if runs else None

# ptr a0010004

MODEL_NAME = os.environ.get("SPARK_MODEL", "qwen3-coder-next")
MIN_OLLAMA_VERSION = "0.15.5"

SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
SESSION_LOG = LOGS_DIR / f"session_{SESSION_ID}.jsonl"

# ptr a0010005

class UILogHandler(logging.Handler):
    def emit(self, record):
        try:
            broadcast("log", {"level": record.levelname, "msg": record.getMessage(),
                              "logger": record.name})
        except Exception:
            pass

logging.basicConfig(level=logging.WARNING, handlers=[UILogHandler()])
log = logging.getLogger("spark")
log.setLevel(logging.DEBUG)
log.addHandler(UILogHandler())

# ptr a0010006
werkzeug_log = logging.getLogger("werkzeug")
werkzeug_log.handlers = [UILogHandler()]
werkzeug_log.setLevel(logging.INFO)

# ptr a0010007

_clients: list[queue.Queue] = []
_events: list[dict] = []
_ev_lock = threading.Lock()

def broadcast(event_type: str, data: dict):
    # ptr a0010007
    entry = {"type": event_type, "data": data, "ts": datetime.now().isoformat(),
             "session": SESSION_ID}
    is_output = event_type == "step_output"
    with _ev_lock:
        if not is_output:
            _events.append(entry)
            if len(_events) > 10000:
                _events.pop(0)
            try:
                with open(SESSION_LOG, "a") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            except Exception:
                pass
    for q in list(_clients):
        try:
            q.put_nowait(entry)
        except queue.Full:
            pass

def persist_file(directory: Path, prefix: str, ext: str, content: str) -> Path:
    # ptr a0010008
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{prefix}.{ext}"
    name = re.sub(r'[^a-zA-Z0-9_.\-]', '_', name)
    path = directory / name
    while path.exists():
        name = f"{ts}_{uuid.uuid4().hex[:4]}_{prefix}.{ext}"
        name = re.sub(r'[^a-zA-Z0-9_.\-]', '_', name)
        path = directory / name
    path.write_text(content)
    return path

# ptr a0010009

VALID_ID = re.compile(r'^[a-z][a-z0-9_]{0,63}$')

BLOCKED_PATTERNS = [
    r'curl\s.*\|\s*(?:sudo\s+)?(?:bash|sh)',
    r'wget\s.*\|\s*(?:sudo\s+)?(?:bash|sh)',
    r'rm\s+-rf\s+/',
    r'mkfs\.',
    r'dd\s+if=',
    r'chmod\s+777\s+/',
    r'>\s*/etc/',
    r'eval\s*\(',
    r'base64\s+-d\s*\|',
    r'nc\s+-[le]',
    r'nohup.*&.*disown',
    r'/dev/tcp/',
    r'python.*-c.*import\s+socket',
]
BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

SAFE_DOMAINS = [
    'localhost', '127.0.0.1', 'host.docker.internal',
    'ghcr.io', 'registry.ollama.ai', 'docker.io',
    'huggingface.co', 'nvcr.io', 'nvidia.com',
    'pypi.org', 'github.com', 'githubusercontent.com',
    'ollama.com', 'ollama.ai',
    'astral.sh',
    'get.docker.com',
]

SAFE_PIPE_PATTERNS = [
    r'https://ollama\.com/install\.sh',
    r'https://get\.docker\.com',
    r'https://astral\.sh/uv/install\.sh',
    r'https://pyenv\.run',
]
SAFE_PIPE_RE = [re.compile(p, re.IGNORECASE) for p in SAFE_PIPE_PATTERNS]

LOCAL_HOSTS = {'localhost', '127.0.0.1', 'host.docker.internal', '0.0.0.0', '::1'}

def scan_command(cmd: str) -> list[str]:
    warnings = []
    for p in BLOCKED_RE:
        if p.search(cmd):
            is_safe = any(sp.search(cmd) for sp in SAFE_PIPE_RE)
            if is_safe:
                warnings.append(f"WARNING: pipe-to-shell but trusted source ({p.pattern})")
            else:
                warnings.append(f"BLOCKED: {p.pattern}")
    if 'sudo ' in cmd:
        warnings.append("WARNING: uses sudo")
    urls = re.findall(r'https?://([^/\s\'"]+)', cmd)
    for h in urls:
        host = h.split(':')[0]
        if not any(host.endswith(d) for d in SAFE_DOMAINS) and host not in LOCAL_HOSTS:
            warnings.append(f"WARNING: unfamiliar host {h}")

    pipe_to_python = re.findall(r'(?:curl|wget)\s+[^\|]*?(https?://\S+)[^\|]*\|\s*python', cmd, re.IGNORECASE)
    for url in pipe_to_python:
        host = re.sub(r'https?://', '', url).split('/')[0].split(':')[0]
        if host not in LOCAL_HOSTS:
            warnings.append(f"BLOCKED: remote URL piped to python ({url})")

    return warnings

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "error"

# ptr a001000b

class BuildRegistry:
    # ptr a001000b


    PORT_POOL_START = 7750
    PORT_POOL_END = 7769

    def __init__(self, builds_dir: Path):
        self.dir = builds_dir
        self._active_lock = threading.Lock()

    def list_builds(self) -> list[dict]:
        builds = []
        for p in sorted(self.dir.iterdir(), reverse=True):
            mf = p / "manifest.json"
            if p.is_dir() and mf.exists():
                try:
                    builds.append(json.loads(mf.read_text()))
                except Exception:
                    pass
        return builds

    def _allocate_port(self) -> int:
        # ptr a001000c
        used = set()
        for b in self.list_builds():
            p = b.get("port")
            if p:
                used.add(p)
        for port in range(self.PORT_POOL_START, self.PORT_POOL_END + 1):
            if port not in used:
                return port
        return self.PORT_POOL_START

    def create_build(self, approach: str, steps: list[dict], install_script: str,
                     teardown_script: str) -> dict:
        # ptr a001000d
        bid = "build_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        bdir = self.dir / bid
        bdir.mkdir()

        hash_content = "\n".join(l for l in install_script.split("\n")
                                  if not l.startswith("# Generated"))
        script_hash = sha256(hash_content)

        dup = self._find_duplicate(script_hash)
        port = self._allocate_port()
        short_id = bid.split("_")[-1]

        manifest = {
            "build_id": bid,
            "short_id": short_id,
            "approach": approach,
            "created_at": datetime.now().isoformat(),
            "script_hash": script_hash,
            "duplicate_of": dup,
            "port": port,
            "container_name": f"openwebui-{short_id}",
            "isolation": {
                "venv": f"data/builds/{bid}/venv",
                "port": port,
                "container": f"openwebui-{short_id}",
                "shared": ["ollama_binary", "ollama_models", "gpu", "cuda"],
            },
            "steps": [{"id": s.get("id"), "name": s.get("name"),
                        "status": s.get("status", "unknown")} for s in steps],
            "health_checks": [],
            "status": "new",
            "active": False,
        }

        (bdir / "install.sh").write_text(install_script)
        os.chmod(bdir / "install.sh", 0o755)
        (bdir / "teardown.sh").write_text(teardown_script)
        os.chmod(bdir / "teardown.sh", 0o755)
        (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        if dup:
            broadcast("build_duplicate", {
                "build_id": bid, "duplicate_of": dup, "hash": script_hash,
                "message": f"This build is char-for-char identical to {dup}. "
                           f"That's suspicious — builds should evolve over time.",
            })

        return manifest

    def _find_duplicate(self, script_hash: str) -> str | None:
        for b in self.list_builds():
            if b.get("script_hash") == script_hash:
                return b["build_id"]
        return None

    def record_health_check(self, build_id: str, passed: bool, detail: str):
        # ptr a001000e
        bdir = self.dir / build_id
        mf = bdir / "manifest.json"
        if not mf.exists():
            return
        try:
            m = json.loads(mf.read_text())
            check = {"ts": datetime.now().isoformat(), "passed": passed, "detail": detail}
            m.setdefault("health_checks", []).append(check)

            checks = m["health_checks"]
            if len(checks) >= 2:
                prev_pass = checks[-2]["passed"]
                curr_pass = checks[-1]["passed"]
                if prev_pass and not curr_pass:
                    m["status"] = "degraded"
                    broadcast("build_degraded", {
                        "build_id": build_id,
                        "message": f"Build {build_id} was working but now fails! "
                                   f"Last error: {detail}",
                    })
                elif curr_pass:
                    m["status"] = "healthy"

            mf.write_text(json.dumps(m, indent=2))
        except Exception as e:
            broadcast("error", {"msg": f"Failed to record health check: {e}"})

    def get_build(self, build_id: str) -> dict | None:
        mf = self.dir / build_id / "manifest.json"
        if mf.exists():
            return json.loads(mf.read_text())
        return None

    def get_script(self, build_id: str, which: str) -> str | None:
        p = self.dir / build_id / f"{which}.sh"
        return p.read_text() if p.exists() else None

    def get_active(self) -> dict | None:
        # ptr a001000f
        for b in self.list_builds():
            if b.get("active"):
                return b
        return None

    def activate_build(self, build_id: str) -> dict:
        # ptr a001000f
        with self._active_lock:
            old_active = None
            for b in self.list_builds():
                if b.get("active") and b["build_id"] != build_id:
                    old_active = b["build_id"]
                    self._set_active(b["build_id"], False)
            self._set_active(build_id, True)
            broadcast("build_activated", {
                "build_id": build_id,
                "deactivated": old_active,
                "message": f"Build {build_id} is now active"
                           + (f" (deactivated {old_active})" if old_active else ""),
            })
            return {"old": old_active, "new": build_id}

    def deactivate_build(self, build_id: str):
        with self._active_lock:
            self._set_active(build_id, False)
            broadcast("build_deactivated", {"build_id": build_id})

    def _set_active(self, build_id: str, active: bool):
        mf = self.dir / build_id / "manifest.json"
        if not mf.exists():
            return
        try:
            m = json.loads(mf.read_text())
            m["active"] = active
            mf.write_text(json.dumps(m, indent=2))
        except Exception:
            pass


registry = BuildRegistry(BUILDS_DIR)

# ptr a0010010

_results: dict[str, dict] = {}
_running: set[str] = set()
_attempt_history: dict[str, list] = {}
_step_overrides: dict[str, dict] = {}
_pending_overrides: dict[str, dict] = {}

MAX_SAME_ERROR = 2
MAX_ATTEMPTS = 5


def error_fingerprint(stderr: str) -> str:
    s = stderr.strip().lower()
    s = re.sub(r'[0-9]+', 'N', s)
    s = re.sub(r'/\S+', '/PATH', s)
    s = re.sub(r'\s+', ' ', s)
    lines = [l for l in s.split('\n')
             if any(k in l for k in ['error','fail','not found','denied','no such','timeout'])]
    return lines[-1][:120] if lines else s[-120:]


def detect_loop(step_id: str) -> dict:
    history = _attempt_history.get(step_id, [])
    if len(history) < 2:
        return {"looping": False, "attempts": len(history)}
    if len(history) >= MAX_ATTEMPTS:
        return {"looping": True, "reason": "max_attempts", "attempts": len(history),
                "similar_count": len(history)}
    latest_fp = history[-1]["error_fp"]
    similar = sum(1 for h in history if h["error_fp"] == latest_fp)
    if similar >= MAX_SAME_ERROR:
        return {"looping": True, "reason": "same_error_repeated", "attempts": len(history),
                "similar_count": similar}
    latest_cmd = history[-1]["command"].strip()
    same_cmd = sum(1 for h in history if h["command"].strip() == latest_cmd)
    if same_cmd >= MAX_SAME_ERROR:
        return {"looping": True, "reason": "same_command_repeated", "attempts": len(history),
                "similar_count": same_cmd}
    return {"looping": False, "attempts": len(history)}


def run_command(step_id: str, command: str, timeout: int = 600) -> dict:
    warnings = scan_command(command)
    blocked = [w for w in warnings if w.startswith("BLOCKED")]
    if blocked:
        result = {"step_id": step_id, "status": "blocked", "exit_code": -1,
                  "stdout": "", "stderr": "SECURITY: Command blocked.\n" + "\n".join(blocked),
                  "duration": 0, "ran_at": datetime.now().isoformat()}
        _results[step_id] = result
        broadcast("step_blocked", {"step_id": step_id, "warnings": warnings})
        return result

    if warnings:
        broadcast("step_warning", {"step_id": step_id, "warnings": warnings})

    _running.add(step_id)
    est = _estimate_duration(step_id)
    broadcast("step_running", {"step_id": step_id, "estimate_seconds": est})

    start = time.time()
    stdout_lines = []
    stderr_lines = []
    try:
        env = {**os.environ, "TERM": "dumb"}
        breadcrumb = Path("/tmp/.ollama_path")
        if breadcrumb.exists():
            try:
                ollama_dir = str(Path(breadcrumb.read_text().strip()).parent)
                env["PATH"] = ollama_dir + ":" + env.get("PATH", "")
            except Exception:
                pass
        extra_paths = "/usr/local/bin:/usr/bin:/snap/bin"
        env["PATH"] = extra_paths + ":" + env.get("PATH", "")

        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env, bufsize=1,
        )

        sel = selectors.DefaultSelector()
        if proc.stdout:
            sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
        if proc.stderr:
            sel.register(proc.stderr, selectors.EVENT_READ, "stderr")

        last_broadcast = 0
        while sel.get_map():
            elapsed = time.time() - start
            if elapsed > timeout:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(command, timeout)

            ready = sel.select(timeout=1.0)
            if not ready:
                broadcast("step_output", {
                    "step_id": step_id, "stream": "heartbeat",
                    "elapsed": round(elapsed, 1),
                    "estimate_seconds": est,
                })
                continue

            for key, _ in ready:
                line = key.fileobj.readline()
                if not line:
                    sel.unregister(key.fileobj)
                    continue
                stream = key.data
                stripped = line.rstrip("\n")
                if stream == "stdout":
                    stdout_lines.append(line)
                else:
                    stderr_lines.append(line)

                now = time.time()
                if now - last_broadcast >= 0.25:
                    last_broadcast = now
                    broadcast("step_output", {
                        "step_id": step_id,
                        "stream": stream,
                        "line": stripped[-500:],
                        "elapsed": round(now - start, 1),
                        "estimate_seconds": est,
                    })

        sel.close()
        proc.wait(timeout=max(1, timeout - (time.time() - start)))

        stdout_text = "".join(stdout_lines)[-8000:]
        stderr_text = "".join(stderr_lines)[-4000:]
        duration = round(time.time() - start, 2)

        result = {
            "step_id": step_id,
            "status": "done" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "duration": duration,
            "ran_at": datetime.now().isoformat(),
        }
    except subprocess.TimeoutExpired:
        result = {"step_id": step_id, "status": "timeout", "exit_code": -1,
                  "stdout": "".join(stdout_lines)[-8000:],
                  "stderr": "".join(stderr_lines)[-4000:] + f"\nTimed out after {timeout}s",
                  "duration": timeout, "ran_at": datetime.now().isoformat()}
    except Exception as e:
        result = {"step_id": step_id, "status": "error", "exit_code": -1,
                  "stdout": "".join(stdout_lines)[-8000:],
                  "stderr": str(e),
                  "duration": round(time.time() - start, 2), "ran_at": datetime.now().isoformat()}

    _results[step_id] = result
    _running.discard(step_id)

    _save_timing(step_id, result.get("duration", 0))

    if result.get("exit_code", 0) != 0:
        if step_id not in _attempt_history:
            _attempt_history[step_id] = []
        _attempt_history[step_id].append({
            "command": command, "stderr": result.get("stderr", ""),
            "error_fp": error_fingerprint(result.get("stderr", "")),
            "ts": datetime.now().isoformat(),
        })
        loop = detect_loop(step_id)
        result["loop_info"] = loop
        if loop["looping"]:
            broadcast("loop_detected", {"step_id": step_id, **loop})

    broadcast("step_done", result)
    return result


_STEP_URLS = {
    "start_openwebui": "http://localhost:7733",
    "verify_e2e": "http://localhost:7733",
    "start_chat": "http://localhost:7722",
}
_STEP_SVC = {
    "start_openwebui": ("open-webui", 7733),
    "start_chat": ("chat", 7722),
}

def _register_svc(name: str, port: int):
    svc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "svc")
    try:
        subprocess.Popen([svc_path, "set", name, str(port)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
_opened_urls: set[str] = set()

def _open_browser(url: str):
    if url in _opened_urls:
        return
    _opened_urls.add(url)
    def _do():
        import shutil
        for cmd in ("xdg-open", "firefox", "open"):
            if shutil.which(cmd):
                try:
                    subprocess.Popen([cmd, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    continue
    threading.Thread(target=_do, daemon=True).start()

def verify_step(step_id: str, verify_cmd: str, expect: str = "") -> bool:
    res = run_command(f"{step_id}__verify", verify_cmd, timeout=120)
    passed = res["exit_code"] == 0
    if expect and expect not in (res.get("stdout", "") + res.get("stderr", "")):
        passed = False
    if step_id in _results:
        _results[step_id]["verified"] = passed
        _results[step_id]["verify_output"] = res.get("stdout", "")[:2000]
    else:
        _results[step_id] = {"step_id": step_id, "verified": passed,
                             "verify_output": res.get("stdout", "")[:2000]}
    broadcast("step_verified", {"step_id": step_id, "passed": passed})
    if passed and step_id in _STEP_SVC:
        svc_name, svc_port = _STEP_SVC[step_id]
        _register_svc(svc_name, svc_port)
    return passed


# ptr a0010010

def build_steps():
    return [
        {"id": "detect_arch", "name": "Detect architecture",
         "description": "CPU arch and OS version",
         "command": "uname -m && cat /etc/os-release | head -3",
         "verify": "uname -m", "expect_contains": "", "category": "preflight",
         "teardown": None},
        {"id": "detect_gpu", "name": "Detect GPU",
         "description": "Check for NVIDIA Blackwell GPU",
         "command": "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || echo 'NO_GPU'",
         "verify": "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null",
         "expect_contains": "", "category": "preflight", "teardown": None},
        {"id": "check_memory", "name": "Check memory",
         "description": "Ensure >=20GB free to avoid OOM reboot",
         "command": textwrap.dedent("""\
             AVAIL_GB=$(awk '/MemAvailable/{printf "%.0f", $2/1024/1024}' /proc/meminfo)
             echo "Available: ${AVAIL_GB}GB"
             if [ "$AVAIL_GB" -lt 20 ]; then echo "FAIL: <20GB free"; exit 1; fi
             echo "OK" """),
         "verify": "awk '/MemAvailable/{gb=$2/1024/1024; if(gb>=20) print \"OK\"; else exit 1}' /proc/meminfo",
         "expect_contains": "OK", "category": "preflight", "teardown": None},
        {"id": "check_docker", "name": "Check Docker permissions",
         "description": "Can current user run Docker without sudo?",
         "command": textwrap.dedent("""\
             if docker info >/dev/null 2>&1; then
               echo "OK: Docker works for $(whoami)"
             else
               echo "FAIL: Run 'sudo usermod -aG docker $(whoami)' then log out/in"
               exit 1
             fi"""),
         "verify": "docker info --format '{{.ServerVersion}}' 2>/dev/null",
         "expect_contains": "", "category": "preflight", "teardown": None},
        {"id": "check_ollama", "name": "Check/install Ollama",
         "description": "Verify Ollama is installed and running. Installs and adds to PATH if needed.",
         "command": textwrap.dedent("""\
             # Common locations where ollama gets installed
             OLLAMA_SEARCH="/usr/local/bin /usr/bin /snap/bin $HOME/.local/bin $HOME/bin /opt/ollama/bin"

             OLLAMA_BIN=""
             # Check PATH first
             if command -v ollama >/dev/null 2>&1; then
               OLLAMA_BIN=$(command -v ollama)
             else
               # Search common locations
               for dir in $OLLAMA_SEARCH; do
                 if [ -x "$dir/ollama" ]; then
                   OLLAMA_BIN="$dir/ollama"
                   break
                 fi
               done
             fi

             if [ -z "$OLLAMA_BIN" ]; then
               echo "Ollama not found anywhere. Installing via official installer..."
               curl -fsSL https://ollama.com/install.sh | sh
               echo ""
               hash -r 2>/dev/null
               if command -v ollama >/dev/null 2>&1; then
                 OLLAMA_BIN=$(command -v ollama)
               else
                 for dir in $OLLAMA_SEARCH; do
                   if [ -x "$dir/ollama" ]; then
                     OLLAMA_BIN="$dir/ollama"
                     break
                   fi
                 done
               fi
               if [ -z "$OLLAMA_BIN" ]; then
                 OLLAMA_BIN=$(find / -name ollama -type f -executable 2>/dev/null | head -1)
               fi
               if [ -z "$OLLAMA_BIN" ]; then
                 echo "FAIL: Install script ran but cannot find ollama binary anywhere"
                 exit 1
               fi
               echo "Found ollama at: $OLLAMA_BIN"
             else
               echo "Ollama found at: $OLLAMA_BIN"
             fi

             # Ensure it's on PATH for this session and future steps
             OLLAMA_DIR=$(dirname "$OLLAMA_BIN")
             export PATH="$OLLAMA_DIR:$PATH"

             # If not in a standard PATH dir, create a symlink
             if ! echo "$PATH" | tr ':' '\\n' | grep -qx "$OLLAMA_DIR"; then
               echo "Adding $OLLAMA_DIR to PATH..."
               if [ -w /usr/local/bin ]; then
                 ln -sf "$OLLAMA_BIN" /usr/local/bin/ollama 2>/dev/null && echo "Symlinked to /usr/local/bin/ollama"
               elif sudo ln -sf "$OLLAMA_BIN" /usr/local/bin/ollama 2>/dev/null; then
                 echo "Symlinked to /usr/local/bin/ollama (via sudo)"
               fi
             fi

             # Write breadcrumb — single line, no trailing newline issues
             printf '%s' "$OLLAMA_BIN" > /tmp/.ollama_path

             "$OLLAMA_BIN" --version
             echo ""

             # Now ensure the service is running
             if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
               echo "OK: Ollama service is running"
               curl -sf http://localhost:11434/api/tags | python3 -c '
import json,sys
d=json.load(sys.stdin); models=d.get("models",[])
print(str(len(models)) + " model(s) loaded")
for m in models: print("  - " + m.get("name","?"))
' 2>/dev/null || true
             else
               echo "Ollama installed but service not running. Starting..."
               if systemctl is-active ollama >/dev/null 2>&1; then
                 echo "OK: ollama.service already active"
               elif sudo systemctl start ollama 2>/dev/null; then
                 sleep 2; echo "OK: started via systemctl"
               else
                 echo "Trying ollama serve directly..."
                 nohup "$OLLAMA_BIN" serve >/tmp/ollama_serve.log 2>&1 &
                 sleep 3
                 if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
                   echo "OK: ollama serve started"
                 else
                   echo "FAIL: Could not start Ollama"
                   echo "Check: cat /tmp/ollama_serve.log"
                   exit 1
                 fi
               fi
             fi"""),
         "verify": textwrap.dedent("""\
             # Use breadcrumb if available, otherwise search PATH
             if [ -f /tmp/.ollama_path ]; then
               OLLAMA_BIN=$(tr -d '\\n\\r' < /tmp/.ollama_path)
               export PATH="$(dirname "$OLLAMA_BIN"):$PATH"
             fi
             curl -sf http://localhost:11434/api/tags >/dev/null && echo OK"""),
         "expect_contains": "OK", "category": "preflight",
         "teardown": None},
        {"id": "upgrade_ollama", "name": f"Ensure Ollama >= {MIN_OLLAMA_VERSION}",
         "description": f"qwen3-coder-next requires Ollama {MIN_OLLAMA_VERSION}+ for MoE/SSM support. Upgrades if needed.",
         "command": textwrap.dedent(f"""\
             # Get current version
             if [ -f /tmp/.ollama_path ]; then
               OLLAMA_BIN=$(tr -d '\\n\\r' < /tmp/.ollama_path)
             else
               OLLAMA_BIN=$(command -v ollama 2>/dev/null || echo "")
             fi
             if [ -z "$OLLAMA_BIN" ]; then
               echo "FAIL: Ollama not found. Run the previous step first."
               exit 1
             fi

             CURRENT=$("$OLLAMA_BIN" --version 2>&1 | grep -oP '\\d+\\.\\d+\\.\\d+' | head -1)
             REQUIRED="{MIN_OLLAMA_VERSION}"
             echo "Current Ollama version: $CURRENT"
             echo "Required minimum:       $REQUIRED"

             # Compare versions
             version_ge() {{
               printf '%s\\n%s' "$2" "$1" | sort -V -C
             }}

             if version_ge "$CURRENT" "$REQUIRED"; then
               echo "OK: Ollama $CURRENT meets minimum $REQUIRED"
               exit 0
             fi

             echo "Ollama $CURRENT is too old. Upgrading..."
             curl -fsSL https://ollama.com/install.sh | sh
             hash -r 2>/dev/null

             # Re-find and verify
             if [ -f /tmp/.ollama_path ]; then
               OLLAMA_BIN=$(tr -d '\\n\\r' < /tmp/.ollama_path)
             fi
             if ! command -v ollama &>/dev/null && [ ! -x "$OLLAMA_BIN" ]; then
               OLLAMA_BIN=$(find /usr/local/bin /usr/bin /snap/bin -name ollama -executable 2>/dev/null | head -1)
             fi
             NEW_VER=$("$OLLAMA_BIN" --version 2>&1 | grep -oP '\\d+\\.\\d+\\.\\d+' | head -1)
             echo "Upgraded to: $NEW_VER"

             # Update breadcrumb
             printf '%s' "$OLLAMA_BIN" > /tmp/.ollama_path

             if version_ge "$NEW_VER" "$REQUIRED"; then
               echo "OK: Upgrade successful"
               # Restart the service so the new version takes effect
               if systemctl is-active ollama >/dev/null 2>&1; then
                 sudo systemctl restart ollama 2>/dev/null && echo "Restarted ollama service"
                 sleep 2
               fi
             else
               echo "FAIL: Upgraded to $NEW_VER but still below $REQUIRED"
               exit 1
             fi"""),
         "verify": textwrap.dedent(f"""\
             if [ -f /tmp/.ollama_path ]; then
               OLLAMA_BIN=$(tr -d '\\n\\r' < /tmp/.ollama_path)
             else
               OLLAMA_BIN=$(command -v ollama 2>/dev/null)
             fi
             VER=$("$OLLAMA_BIN" --version 2>&1 | grep -oP '\\d+\\.\\d+\\.\\d+' | head -1)
             printf '%s\\n%s' "{MIN_OLLAMA_VERSION}" "$VER" | sort -V -C && echo "OK: $VER" || echo "FAIL: $VER < {MIN_OLLAMA_VERSION}" """),
         "expect_contains": "OK", "category": "preflight",
         "teardown": None},
        {"id": "pull_model", "name": f"Pull {MODEL_NAME}",
         "description": f"Download {MODEL_NAME} via Ollama. Checks if already pulled.",
         "command": textwrap.dedent(f"""\
             if ollama list 2>/dev/null | grep -qi {MODEL_NAME}; then
               echo "Already pulled"; ollama list | grep -i {MODEL_NAME.split(':')[0]}; exit 0
             fi
             AVAIL=$(awk '/MemAvailable/{{printf "%.0f",$2/1024/1024}}' /proc/meminfo)
             echo "Memory: ${{AVAIL}}GB free"
             if [ "$AVAIL" -lt 30 ]; then
               echo "WARNING: Only ${{AVAIL}}GB free. Large models may cause OOM."
             fi
             ollama pull {MODEL_NAME}"""),
         "verify": f"ollama list | grep -qi {MODEL_NAME} && echo OK",
         "expect_contains": "OK", "category": "model",
         "teardown": f"ollama rm {MODEL_NAME}"},
        {"id": "test_generate", "name": "Test generation",
         "description": f"Send a prompt to {MODEL_NAME}, confirm it responds",
         "command": textwrap.dedent(f"""\
             echo "Testing {MODEL_NAME}..." 
             RESP=$(echo "Reply SPARK_OK" | timeout 120 ollama run {MODEL_NAME} 2>&1) || {{
               echo "FAIL: no response in 120s"; exit 1; }}
             echo "Response: $RESP"
             echo "OK" """),
         "verify": f"echo 'Say OK' | timeout 90 ollama run {MODEL_NAME} 2>/dev/null | head -5",
         "expect_contains": "", "category": "model", "teardown": None},
        {"id": "start_openwebui", "name": "Start Open WebUI",
         "description": "Launch Docker container with Open WebUI (host networking for Ollama access)",
         "timeout": 900,
         "command": textwrap.dedent("""\
             if docker ps --format '{{.Names}}' | grep -q '^open-webui$'; then
               echo "Already running"; docker ps --filter name=open-webui --format 'table {{.Status}}\t{{.Ports}}'; exit 0
             fi
             docker rm -f open-webui 2>/dev/null || true
             echo "Pulling Open WebUI image (this may take several minutes)..."
             docker pull ghcr.io/open-webui/open-webui:main
             echo "Image pulled. Starting container..."
             docker run -d --network=host \
               -e OLLAMA_BASE_URL=http://127.0.0.1:11434 \
               -e PORT=7733 \
               -e WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY:-$(python3 -c "import secrets; print(secrets.token_hex(32))")} \
               -v open-webui:/app/backend/data \
               --name open-webui --restart unless-stopped \
               ghcr.io/open-webui/open-webui:main
             echo "Waiting for Open WebUI to become ready (up to 3 min)..."
             for i in $(seq 1 36); do
               curl -sf http://localhost:7733/health -o /dev/null 2>/dev/null && { echo "OK: up"; exit 0; }
               [ $((i % 6)) -eq 0 ] && echo "  Still waiting... ($(( i * 5 ))s)" && docker logs --tail 3 open-webui 2>&1
               sleep 5
             done
             echo "FAIL: not responding after 3 min"
             docker logs --tail 20 open-webui
             exit 1"""),
         "verify": "curl -sf http://localhost:7733/health -o /dev/null && echo UP",
         "expect_contains": "UP", "category": "ui",
         "teardown": "docker rm -f open-webui 2>/dev/null; docker volume rm open-webui 2>/dev/null"},
        {"id": "verify_e2e", "name": "Verify end-to-end",
         "description": "WebUI + Ollama connected and working",
         "command": textwrap.dedent("""\
             curl -sf http://localhost:7733 -o /dev/null || { echo "FAIL: WebUI down"; exit 1; }
             echo "WebUI: OK"
             curl -sf http://localhost:11434/api/tags | python3 -c '
import json,sys
d=json.load(sys.stdin); models=d.get("models",[])
for m in models: print("  Model: " + m.get("name","?"))
print(str(len(models)) + " model(s)")
' || echo "WARN: Could not list models"
             echo "Open http://localhost:7733 to start chatting"
             echo "ALL_OK" """),
         "verify": "curl -sf http://localhost:7733 -o /dev/null && curl -sf http://localhost:11434/api/tags -o /dev/null && echo ALL_OK",
         "expect_contains": "ALL_OK", "category": "ui", "teardown": None},
        {"id": "start_chat", "name": "Start Magic Factory Chat",
         "description": "Launch the local chat UI (no auth, no Docker, direct Ollama)",
         "command": textwrap.dedent(f"""\
             CHAT_DIR="$(dirname "$(realpath "$0")" 2>/dev/null || echo ".")/chat"
             # Fallback: find chat.py relative to this script's actual location
             for d in "{BASE}/chat" "./chat" "../chat"; do
               if [ -f "$d/chat.py" ]; then CHAT_DIR="$d"; break; fi
             done

             if [ ! -f "$CHAT_DIR/chat.py" ]; then
               echo "FAIL: chat/chat.py not found"
               exit 1
             fi

             # Kill any existing instance
             if [ -f "$CHAT_DIR/.chat.pid" ]; then
               kill $(cat "$CHAT_DIR/.chat.pid") 2>/dev/null || true
               rm -f "$CHAT_DIR/.chat.pid"
             fi

             python3 "$CHAT_DIR/chat.py" --model {MODEL_NAME} --port 7722 >/dev/null 2>&1 &
             CHAT_PID=$!
             echo "$CHAT_PID" > "$CHAT_DIR/.chat.pid"
             sleep 2

             if curl -sf http://localhost:7722/ -o /dev/null 2>&1; then
               echo "OK: Magic Factory Chat running at http://localhost:7722"
               echo "PID: $CHAT_PID"
             else
               echo "FAIL: Magic Factory Chat did not start"
               kill $CHAT_PID 2>/dev/null || true
               exit 1
             fi"""),
         "verify": "curl -sf http://localhost:7722/ -o /dev/null && echo OK",
         "expect_contains": "OK", "category": "ui",
         "teardown": f"kill $(cat {BASE}/chat/.chat.pid 2>/dev/null) 2>/dev/null; rm -f {BASE}/chat/.chat.pid"},
    ]


# ptr a0010019

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a DGX Spark setup expert. DGX Spark: ARM64/aarch64, Ubuntu 24.04,
    CUDA 13.0, sm_121 Blackwell GPU, 128GB unified LPDDR5x, Ollama+Docker pre-installed.
    Give concrete shell commands. Account for ARM64 and sm_121 quirks. Be brief.
    IMPORTANT: Do NOT suggest commands identical to previous failed attempts.
    Each suggestion must be meaningfully different from what was tried before.""")


def claude_ask(step_name: str, command: str, stderr: str, step_id: str = None) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "No ANTHROPIC_API_KEY set."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        history_text = ""
        loop_info = {"looping": False, "attempts": 0}
        if step_id and step_id in _attempt_history:
            h = _attempt_history[step_id]
            history_text = f"\n\nPrevious {len(h)} attempt(s):\n" + "\n".join(
                f"  #{i+1} cmd: {a['command'][:100]}  err: {a['stderr'][:200]}"
                for i, a in enumerate(h[-5:]))
            loop_info = detect_loop(step_id)

        if loop_info.get("looping"):
            prompt = f"""STUCK IN A LOOP on DGX Spark step "{step_name}".
Tried {loop_info['attempts']} times, same error.
{history_text}

The current approach DOES NOT WORK. Give a COMPLETELY DIFFERENT approach.
Do NOT repeat any previous command. Format:
NEW_COMMAND: <the different command>
EXPLANATION: <why this will work>"""
        else:
            prompt = f"""Step "{step_name}" failed on DGX Spark.
Command: {command}
Error: {stderr[:3000]}
{history_text}

Fix it. If suggesting a new command, format as:
NEW_COMMAND: <command>
EXPLANATION: <why>"""

        prev_builds = registry.list_builds()
        if prev_builds:
            prompt += f"\n\nNote: {len(prev_builds)} previous build(s) exist. Your solution should be an improvement, not a copy."

        model = "claude-opus-4-6" if loop_info.get("looping") else "claude-sonnet-4-6"
        resp = client.messages.create(model=model, max_tokens=2048,
                                       system=SYSTEM_PROMPT,
                                       messages=[{"role": "user", "content": prompt}])
        advice = resp.content[0].text

        if step_id and "NEW_COMMAND:" in advice:
            cmd_text = advice.split("NEW_COMMAND:")[1].split("EXPLANATION:")[0]
            new_cmd = "\n".join(l.strip() for l in cmd_text.strip().split("\n")
                                if l.strip() and not l.strip().startswith("```"))
            if new_cmd:
                warnings = scan_command(new_cmd)
                blocked = [w for w in warnings if w.startswith("BLOCKED")]
                if blocked:
                    advice += "\n\n⚠ SECURITY: Suggested command BLOCKED: " + "; ".join(blocked)
                    _pending_overrides[step_id] = {
                        "command": new_cmd, "source": "claude",
                        "reason": f"BLOCKED — needs human approval",
                        "ts": datetime.now().isoformat(), "security_warnings": warnings}
                    broadcast("override_blocked", {"step_id": step_id, "command": new_cmd,
                                                    "warnings": warnings})
                else:
                    _step_overrides[step_id] = {
                        "command": new_cmd, "source": "claude",
                        "reason": f"Auto-applied after {loop_info.get('attempts',1)} attempt(s)",
                        "ts": datetime.now().isoformat(), "security_warnings": warnings}
                    broadcast("override_applied", {"step_id": step_id, "command": new_cmd,
                                                     "warnings": warnings})

        persist_file(RESEARCH_DIR, f"{step_id or 'general'}_claude", "txt", advice)
        return advice
    except Exception as e:
        return f"Claude error: {e}"


# ptr a001001a

def health_check_loop():
    # ptr a001001a
    while True:
        try:
            sleep_hours = 6 + random.random() * 6
            time.sleep(sleep_hours * 3600)

            builds = registry.list_builds()
            healthy_builds = [b for b in builds if b.get("status") in ("healthy", "new")]

            if not healthy_builds:
                continue

            build = random.choice(healthy_builds)
            bid = build["build_id"]
            broadcast("health_check_start", {"build_id": bid})

            ok = True
            detail = ""
            for step in build_steps():
                if step["id"] in ("verify_e2e", "start_openwebui"):
                    res = run_command(f"health_{bid}_{step['id']}", step["verify"], timeout=60)
                    if res["exit_code"] != 0:
                        ok = False
                        detail = res.get("stderr", "")[:500]
                        break
                    else:
                        detail = "All checks passed"

            registry.record_health_check(bid, ok, detail)
            broadcast("health_check_done", {"build_id": bid, "passed": ok, "detail": detail})

        except Exception as e:
            broadcast("error", {"msg": f"Health check error: {e}"})


# ptr a001001b

app = Flask(__name__, template_folder=str(BASE / "templates"),
            static_folder=str(BASE / "static"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/steps")
def api_steps():
    steps = build_steps()
    for s in steps:
        sid = s["id"]
        s["result"] = _results.get(sid, {})
        s["is_running"] = sid in _running
        s["attempts"] = len(_attempt_history.get(sid, []))
        s["loop_info"] = detect_loop(sid) if _attempt_history.get(sid) else {"looping": False, "attempts": 0}
        if sid in _step_overrides:
            s["original_command"] = s["command"]
            s["command"] = _step_overrides[sid]["command"]
            s["override_source"] = _step_overrides[sid].get("source")
        if sid in _pending_overrides:
            s["pending_override"] = _pending_overrides[sid]
    return jsonify({"steps": steps, "autorun": _autorun_active})

@app.route("/api/run/<step_id>", methods=["POST"])
def api_run(step_id):
    if not VALID_ID.match(step_id):
        return jsonify({"error": "Invalid step ID"}), 400
    steps = {s["id"]: s for s in build_steps()}
    if step_id not in steps:
        return jsonify({"error": "Unknown step"}), 404
    if step_id in _running:
        return jsonify({"error": "Already running"}), 409
    step = steps[step_id]
    cmd = _step_overrides.get(step_id, {}).get("command") or step["command"]
    step_timeout = step.get("timeout", 600)
    threading.Thread(target=run_command, args=(step_id, cmd), kwargs={"timeout": step_timeout}, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/verify/<step_id>", methods=["POST"])
def api_verify(step_id):
    if not VALID_ID.match(step_id):
        return jsonify({"error": "Invalid step ID"}), 400
    steps = {s["id"]: s for s in build_steps()}
    if step_id not in steps:
        return jsonify({"error": "Unknown step"}), 404
    step = steps[step_id]
    v = _step_overrides.get(step_id, {}).get("verify") or step["verify"]
    passed = verify_step(step_id, v, step.get("expect_contains", ""))
    return jsonify({"passed": passed})

@app.route("/api/ask-claude/<step_id>", methods=["POST"])
def api_ask(step_id):
    if not VALID_ID.match(step_id):
        return jsonify({"error": "Invalid step ID"}), 400
    steps = {s["id"]: s for s in build_steps()}
    if step_id not in steps:
        return jsonify({"error": "Unknown step"}), 404
    step = steps[step_id]
    r = _results.get(step_id, {})
    cmd = _step_overrides.get(step_id, {}).get("command") or step["command"]
    advice = claude_ask(step["name"], cmd, r.get("stderr", "") or r.get("stdout", ""), step_id)
    return jsonify({"advice": advice})

@app.route("/api/approve/<step_id>", methods=["POST"])
def api_approve(step_id):
    if not VALID_ID.match(step_id):
        return jsonify({"error": "Invalid step ID"}), 400
    if step_id not in _pending_overrides:
        return jsonify({"error": "No pending override"}), 404
    _step_overrides[step_id] = _pending_overrides.pop(step_id)
    broadcast("override_approved", {"step_id": step_id})
    return jsonify({"status": "approved"})

@app.route("/api/reject/<step_id>", methods=["POST"])
def api_reject(step_id):
    if not VALID_ID.match(step_id):
        return jsonify({"error": "Invalid step ID"}), 400
    _pending_overrides.pop(step_id, None)
    broadcast("override_rejected", {"step_id": step_id})
    return jsonify({"status": "rejected"})

@app.route("/api/reset/<step_id>", methods=["POST"])
def api_reset(step_id):
    if not VALID_ID.match(step_id):
        return jsonify({"error": "Invalid step ID"}), 400
    for d in (_step_overrides, _pending_overrides, _attempt_history, _results):
        d.pop(step_id, None)
    _running.discard(step_id)
    broadcast("step_reset", {"step_id": step_id})
    return jsonify({"status": "reset"})

@app.route("/api/reset-all", methods=["POST"])
def api_reset_all():
    global _autorun_active
    _autorun_active = False
    for d in (_step_overrides, _pending_overrides, _attempt_history, _results):
        d.clear()
    _running.clear()
    broadcast("all_reset", {"msg": "All steps reset to startup state"})
    return jsonify({"status": "reset"})

_autorun_active = False
_autorun_lock = threading.Lock()

@app.route("/api/autorun", methods=["POST"])
def api_autorun():
    global _autorun_active
    with _autorun_lock:
        if _autorun_active:
            return jsonify({"error": "Autorun already in progress"}), 409
        _autorun_active = True
    threading.Thread(target=_autorun_worker, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/autorun/stop", methods=["POST"])
def api_autorun_stop():
    global _autorun_active
    _autorun_active = False
    broadcast("autorun_stopped", {"msg": "Autorun will stop after current step"})
    return jsonify({"status": "stopping"})

def _autorun_worker():
    global _autorun_active
    try:
        steps = build_steps()
        broadcast("autorun_start", {"msg": f"Starting autorun: {len(steps)} steps"})

        for i, step in enumerate(steps):
            if not _autorun_active:
                broadcast("autorun_stopped", {"msg": f"Stopped before step {step['name']}"})
                return

            sid = step["id"]
            broadcast("autorun_step", {"step_id": sid, "index": i + 1,
                                        "total": len(steps), "name": step["name"]})

            cmd = _step_overrides.get(sid, {}).get("command") or step["command"]
            step_timeout = step.get("timeout", 600)
            result = run_command(sid, cmd, timeout=step_timeout)

            if not _autorun_active:
                return

            if result.get("exit_code", 0) != 0:
                broadcast("autorun_error", {"step_id": sid, "msg": f"Step failed, asking Claude..."})
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if api_key:
                    claude_ask(step["name"], cmd,
                              result.get("stderr", "") or result.get("stdout", ""), sid)
                    if sid in _step_overrides:
                        new_cmd = _step_overrides[sid]["command"]
                        broadcast("autorun_retry", {"step_id": sid, "msg": "Retrying with Claude suggestion"})
                        result = run_command(sid, new_cmd, timeout=step_timeout)

            if not _autorun_active:
                return

            v_cmd = _step_overrides.get(sid, {}).get("verify") or step["verify"]
            passed = verify_step(sid, v_cmd, step.get("expect_contains", ""))

            if not passed:
                broadcast("autorun_failed", {
                    "step_id": sid, "name": step["name"],
                    "msg": f"Step '{step['name']}' failed verification. Stopping autorun."})
                _autorun_active = False
                return

        broadcast("autorun_complete", {"msg": "All steps passed!"})
    except Exception as e:
        broadcast("autorun_error", {"msg": f"Autorun error: {e}"})
    finally:
        _autorun_active = False

@app.route("/api/export", methods=["POST"])
def api_export():
    steps = build_steps()
    verified = [s for s in steps if _results.get(s["id"], {}).get("verified")]
    if not verified:
        return jsonify({"error": "No verified steps to export"}), 400

    install_lines = ["#!/usr/bin/env bash", "set -euo pipefail",
                     f"# Generated {datetime.now().isoformat()}", ""]
    for s in steps:
        r = _results.get(s["id"], {})
        if not r.get("verified"):
            install_lines.append(f"# SKIP (not verified): {s['name']}")
            continue
        cmd = _step_overrides.get(s["id"], {}).get("command") or s["command"]
        install_lines.append(f"echo '=== {s['name']} ==='")
        install_lines.append(cmd.strip())
        install_lines.append("")
    install_script = "\n".join(install_lines)

    teardowns = [(s["name"], s["teardown"]) for s in reversed(steps) if s.get("teardown")]
    td_lines = ["#!/usr/bin/env bash", "set -uo pipefail",
                 f"# Generated {datetime.now().isoformat()}", "",
                 'KEEP_MODELS=false; KEEP_IMAGES=false; DRY_RUN=false',
                 'for a in "$@"; do case $a in --keep-models) KEEP_MODELS=true;; --keep-images) KEEP_IMAGES=true;; --dry-run) DRY_RUN=true;; esac; done', ""]
    for name, cmd in teardowns:
        td_lines.append(f"echo 'Removing: {name}'")
        td_lines.append(f'[ "$DRY_RUN" = true ] && echo "[dry] {cmd}" || {cmd}')
        td_lines.append("")
    teardown_script = "\n".join(td_lines)

    manifest = registry.create_build("ollama+openwebui", [_results.get(s["id"], {}) for s in steps],
                                      install_script, teardown_script)
    broadcast("build_created", manifest)
    return jsonify(manifest)

@app.route("/api/builds")
def api_builds():
    builds = registry.list_builds()
    return jsonify(builds)

@app.route("/api/builds/active")
def api_active_build():
    active = registry.get_active()
    return jsonify(active) if active else jsonify(None)

@app.route("/api/builds/<build_id>/activate", methods=["POST"])
def api_activate(build_id):
    b = registry.get_build(build_id)
    if not b:
        return jsonify({"error": "Build not found"}), 404
    result = registry.activate_build(build_id)
    return jsonify(result)

@app.route("/api/builds/<build_id>/deactivate", methods=["POST"])
def api_deactivate(build_id):
    registry.deactivate_build(build_id)
    return jsonify({"status": "deactivated"})

@app.route("/api/builds/<build_id>")
def api_build_detail(build_id):
    if not VALID_ID.match(build_id.replace("build_", "").replace("-", "_")[:64]):
        return jsonify({"error": "Invalid build ID"}), 400
    b = registry.get_build(build_id)
    return jsonify(b) if b else (jsonify({"error": "Not found"}), 404)

@app.route("/api/builds/<build_id>/<which>")
def api_build_script(build_id, which):
    if which not in ("install", "teardown"):
        return jsonify({"error": "Must be install or teardown"}), 400
    script = registry.get_script(build_id, which)
    return (script, 200, {"Content-Type": "text/plain"}) if script else ("Not found", 404)

@app.route("/api/events")
def api_events():
    q = queue.Queue(maxsize=500)
    _clients.append(q)
    def stream():
        try:
            while True:
                try:
                    yield f"data: {json.dumps(q.get(timeout=25), default=str)}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'type':'ping'})}\n\n"
        except GeneratorExit:
            if q in _clients:
                _clients.remove(q)
    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/logs")
def api_logs():
    all_events = []
    for logfile in sorted(LOGS_DIR.glob("session_*.jsonl"), reverse=True)[:5]:
        try:
            for line in logfile.read_text().strip().split("\n"):
                if line:
                    all_events.append(json.loads(line))
        except Exception:
            pass
    return jsonify(all_events[-1000:])

@app.route("/api/services")
def api_services():
    """Return live status of all known services."""
    import socket as _sock
    services = [
        {"id": "harness",   "label": "Magic Factory",   "port": 7711, "description": "Build harness & orchestration dashboard — you are here", "type": "process"},
        {"id": "chat",      "label": "Magic Factory Chat", "port": 7722, "description": "Direct local chat with your downloaded model via Ollama — no cloud, no accounts", "type": "process"},
        {"id": "open-webui","label": "Open WebUI",      "port": 7733, "description": "Full-featured chat UI with model management, prompt library, and RAG — runs in Docker", "type": "docker"},
    ]
    for svc in services:
        port = svc["port"]
        try:
            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                s.settimeout(0.4)
                svc["running"] = s.connect_ex(("127.0.0.1", port)) == 0
        except Exception:
            svc["running"] = False
        svc["url"] = f"http://localhost:{port}"
    return jsonify(services)

@app.route("/api/credits")
def api_credits():
    """Easter egg: who made this thing?"""
    return jsonify({
        "project": "NVIDIA DGX Spark Magic Factory",
        "author": "Chris Morley",
        "company": "Lantern Light AI",
        "website": "https://www.lanternlight.ai",
        "email": "chris.morley@lanternlight.ai",
        "personal_email": "depahelix@gmail.com",
        "location": "Massachusetts, USA",
        "made_with": "love",
        "available_for": "contracts & 100% remote work",
        "message": "If you found this, you're the kind of person I'd love to work with.",
    })

@app.route("/api/integrity")
def api_integrity():
    files = ["app.py", "bin/start.sh", "bin/stop.sh", "chat/chat.py", "requirements.txt", "templates/index.html", "static/style.css"]
    return jsonify({
        "session": SESSION_ID,
        "hashes": {f: file_sha256(str(BASE / f)) for f in files if (BASE / f).exists()},
    })


# ptr a001001f

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7711)
    args = parser.parse_args()

    class UIWriter:
        def __init__(self, level):
            self.level = level
            self.buf = ""
        def write(self, s):
            self.buf += s
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                if line.strip():
                    broadcast("stdio", {"level": self.level, "msg": line})
        def flush(self):
            if self.buf.strip():
                broadcast("stdio", {"level": self.level, "msg": self.buf})
                self.buf = ""
        def isatty(self):
            return False

    sys.stdout = UIWriter("stdout")
    sys.stderr = UIWriter("stderr")

    threading.Thread(target=health_check_loop, daemon=True).start()

    broadcast("system", {"msg": f"NVIDIA DGX Spark Magic Factory starting. Session: {SESSION_ID}",
                          "port": args.port})

    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", args.port, app, threaded=True)
    broadcast("system", {"msg": f"Listening on http://localhost:{args.port}"})

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        broadcast("system", {"msg": "Shutting down"})
        server.shutdown()


if __name__ == "__main__":
    main()
