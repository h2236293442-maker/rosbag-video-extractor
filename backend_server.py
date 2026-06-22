#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
SCRIPT_PATH = str(BASE_DIR / "exact_bag_png_mutil_process_slave01.py")
HOST = "127.0.0.1"
PORT = 8765


class Runner:
    def __init__(self):
        self.proc = None
        self.logs = []
        self.lock = threading.Lock()
        self.running = False
        self.exit_code = None

    def _append(self, level, msg):
        with self.lock:
            self.logs.append(
                {
                    "ts": time.strftime("%H:%M:%S", time.localtime()),
                    "level": level,
                    "message": msg.rstrip("\n"),
                }
            )

    def _cleanup_temp_media(self):
        base_dir = Path(SCRIPT_PATH).parent
        patterns = ("temp_*.h264", "temp_*.mp4")
        removed = 0
        for pattern in patterns:
            for file_path in base_dir.glob(pattern):
                try:
                    file_path.unlink()
                    removed += 1
                except Exception:
                    pass
        if removed:
            self._append("INFO", f"已清理临时转码文件: {removed} 个")

    def start(self, payload):
        with self.lock:
            if self.running:
                raise RuntimeError("已有任务正在运行")
            # 新任务启动时清空历史日志，避免前端混入旧任务内容
            self.logs = []
            self.exit_code = None

        mode = payload.get("mode", "single")
        path = payload.get("path", "")
        save_dir = payload.get("save_dir", "")
        topics = payload.get("topics", [])
        sample_enable = bool(payload.get("sample_enable", False))
        sample_mode = payload.get("sample_mode", "frame")
        sample_interval = float(payload.get("sample_interval", 1))

        if not os.path.exists(SCRIPT_PATH):
            raise RuntimeError(f"脚本不存在: {SCRIPT_PATH}")
        if not path:
            raise RuntimeError("缺少 path")
        if not save_dir:
            raise RuntimeError("缺少 save_dir")

        cmd = [
            sys.executable,
            "-u",
            SCRIPT_PATH,
            "--mode",
            mode,
            "--path",
            path,
            "--save-dir",
            save_dir,
        ]
        for topic in topics:
            cmd.extend(["--camera-topic", topic])
        if sample_enable:
            cmd.extend(
                [
                    "--sample-enable",
                    "--sample-mode",
                    sample_mode,
                    "--sample-interval",
                    str(sample_interval),
                ]
            )

        self._append("INFO", f"执行命令: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        with self.lock:
            self.proc = proc
            self.running = True
            self.exit_code = None

        def _read_stdout():
            assert proc.stdout is not None
            for line in proc.stdout:
                self._append("INFO", line)

        def _read_stderr():
            assert proc.stderr is not None
            for line in proc.stderr:
                self._append("ERROR", line)

        def _waiter():
            out_t = threading.Thread(target=_read_stdout, daemon=True)
            err_t = threading.Thread(target=_read_stderr, daemon=True)
            out_t.start()
            err_t.start()
            code = proc.wait()
            out_t.join(timeout=0.5)
            err_t.join(timeout=0.5)
            with self.lock:
                self.running = False
                self.exit_code = code
                self.proc = None
            self._cleanup_temp_media()
            self._append("INFO" if code == 0 else "ERROR", f"进程结束，退出码: {code}")

        threading.Thread(target=_waiter, daemon=True).start()

    def stop(self):
        with self.lock:
            proc = self.proc
        if not proc:
            return False
        proc.terminate()
        self._append("WARN", "收到停止请求，正在终止进程...")
        return True

    def get_logs(self, offset):
        with self.lock:
            total = len(self.logs)
            rows = self.logs[offset:total] if 0 <= offset <= total else self.logs
            return {
                "offset": offset,
                "new_offset": total,
                "lines": rows,
                "running": self.running,
                "exit_code": self.exit_code,
            }


RUNNER = Runner()


def choose_path(kind, multi=False):
    if kind == "dir":
        script = 'POSIX path of (choose folder with prompt "请选择目录")'
    elif kind == "file":
        if multi:
            script = (
                'set pickedFiles to choose file with prompt "请选择文件" with multiple selections allowed\n'
                "set outList to {}\n"
                "repeat with f in pickedFiles\n"
                "set end of outList to POSIX path of f\n"
                "end repeat\n"
                "set AppleScript's text item delimiters to \"\\n\"\n"
                "return outList as text"
            )
        else:
            script = 'POSIX path of (choose file with prompt "请选择文件")'
    else:
        return []

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip()
        if not output:
            return []
        if multi:
            return [line for line in output.splitlines() if line.strip()]
        return [output]
    except subprocess.CalledProcessError:
        return []


def list_preview_images(root_dir):
    if not root_dir:
        return []
    root = Path(root_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    groups = {}
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in exts:
            continue
        parent_name = file_path.parent.name or "root"
        key = parent_name
        if key not in groups:
            groups[key] = []
        groups[key].append(
            {
                "name": file_path.name,
                "path": str(file_path.resolve()),
            }
        )
    payload = []
    for key, frames in groups.items():
        payload.append({"key": key, "label": key, "frames": frames})
    return payload


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path):
        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            self._send(404, {"ok": False, "error": "file not found"})
            return
        raw = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_frontend_file(self, name):
        path = (FRONTEND_DIR / name).resolve()
        if FRONTEND_DIR.resolve() not in path.parents or not path.is_file():
            self._send(404, {"ok": False, "error": "not found"})
            return
        raw = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        static_files = {
            "/": "index.html",
            "/index.html": "index.html",
            "/app.js": "app.js",
            "/styles.css": "styles.css",
        }
        if parsed.path in static_files:
            self._send_frontend_file(static_files[parsed.path])
            return
        if parsed.path == "/api/health":
            self._send(
                200,
                {
                    "ok": True,
                    "script_exists": os.path.exists(SCRIPT_PATH),
                    "running": RUNNER.running,
                },
            )
            return
        if parsed.path == "/api/logs":
            offset = int(qs.get("offset", ["0"])[0])
            self._send(200, {"ok": True, **RUNNER.get_logs(offset)})
            return
        if parsed.path == "/api/select":
            kind = qs.get("kind", ["dir"])[0]
            multi = qs.get("multi", ["0"])[0] == "1"
            paths = choose_path(kind=kind, multi=multi)
            self._send(200, {"ok": True, "paths": paths})
            return
        if parsed.path == "/api/preview/list":
            root_dir = qs.get("dir", [""])[0]
            topics = list_preview_images(root_dir)
            self._send(200, {"ok": True, "topics": topics})
            return
        if parsed.path == "/api/preview/file":
            file_path = qs.get("path", [""])[0]
            self._send_file(file_path)
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_len) if content_len > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8") or "{}")

        if parsed.path == "/api/run":
            try:
                RUNNER.start(payload)
                self._send(200, {"ok": True})
            except Exception as e:
                self._send(400, {"ok": False, "error": str(e)})
            return
        if parsed.path == "/api/stop":
            stopped = RUNNER.stop()
            self._send(200, {"ok": True, "stopped": stopped})
            return
        self._send(404, {"ok": False, "error": "not found"})


if __name__ == "__main__":
    print(f"Backend running on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
