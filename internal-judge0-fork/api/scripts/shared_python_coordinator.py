"""Trusted, test-only coordinator for one sandboxed Python submission process."""

import base64
import fcntl
import hashlib
import json
import os
import selectors
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PYTHON = "/opt/python/bin/python3.14"
MAX_PROTOCOL_BYTES = 4 * 1024 * 1024
MAX_FRAME_BYTES = 4 * 1024 * 1024
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def emit(event):
    sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def emit_stage(stage, started):
    emit({"type": "stage", "stage": stage, "seconds": time.monotonic() - started})


class ProtocolError(Exception):
    pass


def read_exact(stream, size):
    chunks = []
    while size:
        chunk = stream.recv(size)
        if not chunk:
            raise EOFError("stream closed")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


class FrameReader:
    def __init__(self, session):
        self.session = session
        self.buffer = bytearray()
        self.total = 0

    def read_line(self, deadline):
        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self.buffer[:newline])
                del self.buffer[: newline + 1]
                return line
            if len(self.buffer) > MAX_FRAME_BYTES:
                raise ProtocolError("case frame exceeded output bound")
            chunk = self.session.read_chunk(deadline)
            if chunk is None:
                if self.buffer:
                    raise ProtocolError("partial case frame")
                return None
            self.total += len(chunk)
            if self.total > MAX_PROTOCOL_BYTES:
                raise ProtocolError("submission output exceeded aggregate bound")
            self.buffer.extend(chunk)


class IsolateSession:
    def __init__(self, config):
        self.config = config
        self.lock = None
        self.slot = None
        self.temp = None
        self.process = None
        self.stderr_bytes = 0
        self.stderr_overflow = False
        self._open()

    def _open(self):
        for slot in range(1000):
            lock = open(f"/run/isolate/slots/{slot}", "w", encoding="utf-8")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                continue
            self.lock = lock
            self.slot = slot
            break
        if self.slot is None:
            raise RuntimeError("no sandbox slots available")
        slot = str(self.slot)
        # A previous coordinator may have died after its process was killed.
        subprocess.run(
            ["isolate", "--cg", "-b", slot, "--cleanup"], capture_output=True
        )
        started = time.monotonic()
        result = subprocess.run(
            ["isolate", "--cg", "-b", slot, "--init"],
            capture_output=True,
            text=True,
            check=True,
        )
        emit_stage("sandbox_initialization", started)
        path = result.stdout.strip()
        if path != f"/var/local/lib/isolate/{slot}":
            raise RuntimeError("unexpected sandbox path")
        Path(path, "box", "script.py").write_text(self.config["script"])
        self.temp = tempfile.TemporaryDirectory(prefix="shared-execution-")
        metadata = Path(self.temp.name, "metadata")
        limits = self.config["limits"]
        args = [
            "isolate",
            "-s",
            "--cg",
            "-b",
            slot,
            "-M",
            str(metadata),
            "-t",
            str(limits["cpu"]),
            "-x",
            str(limits["cpu_extra"]),
            "-w",
            str(limits["wall"]),
            "-k",
            str(limits["stack_kb"]),
            f"-p{limits['processes']}",
            f"--cg-mem={limits['memory_kb']}",
            "-f",
            str(limits["file_kb"]),
            "--no-default-dirs",
            "--dir=box=./box:rw",
            "--dir=tmp:tmp",
            "--dir=lib=/usr/lib",
            "--dir=lib64=/usr/lib64:maybe",
            "--dir=usr/lib=/usr/lib",
            "--dir=opt/python=/opt/python",
            "-E",
            "HOME=/tmp",
            "-E",
            "LANG=C.UTF-8",
            "--run",
            "--",
            PYTHON,
            "-I",
            "-B",
            "script.py",
        ]
        self.process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self):
        while chunk := self.process.stderr.read(4096):
            self.stderr_bytes += len(chunk)
            self.stderr_overflow |= self.stderr_bytes > 65536

    def send_case(self, index, value, limit):
        packet = (
            json.dumps(
                {"index": index, "input": value, "output_limit_bytes": limit},
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        self.process.stdin.write(packet)
        self.process.stdin.flush()

    def read_chunk(self, deadline):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            ready = selector.select(max(0, deadline - time.monotonic()))
        if not ready:
            raise TimeoutError("shared sandbox deadline exceeded")
        chunk = os.read(self.process.stdout.fileno(), 4096)
        return chunk or None

    def finish(self, deadline):
        self.process.stdin.close()
        remaining = max(0, deadline - time.monotonic())
        try:
            self.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("shared sandbox deadline exceeded") from error
        metadata = {}
        path = Path(self.temp.name, "metadata")
        if path.exists():
            for line in path.read_text(errors="replace").splitlines():
                key, _, value = line.partition(":")
                metadata[key] = value
        if self.stderr_overflow:
            return {"termination": "output", "time": None, "memory": None}
        state = metadata.get("status")
        termination = (
            "timeout"
            if state == "TO"
            else "fatal"
            if state in {"RE", "SG"}
            else "unknown"
            if state == "XX" or not metadata
            else "complete"
        )
        return {
            "termination": termination,
            "time": metadata.get("time"),
            "memory": metadata.get("cg-mem"),
        }

    def close(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)
        if self.slot is not None:
            started = time.monotonic()
            result = subprocess.run(
                ["isolate", "--cg", "-b", str(self.slot), "--cleanup"],
                capture_output=True,
            )
            emit_stage("sandbox_cleanup", started)
            if result.returncode:
                emit({"type": "cleanup_error"})
        if self.temp:
            self.temp.cleanup()
        if self.lock:
            self.lock.close()


class GoStreamSession:
    def __init__(self, config):
        self.config = config
        self.socket = None
        self.response = None
        self.stderr_bytes = 0
        self.stderr_overflow = False
        self._open()

    def _open(self):
        started = time.monotonic()
        host, port = "127.0.0.1", 5050
        self.socket = socket.create_connection((host, port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET /stream HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode())
        headers = bytearray()
        while not headers.endswith(b"\r\n\r\n"):
            if len(headers) > 8192:
                raise ProtocolError("websocket handshake too large")
            headers.extend(read_exact(self.socket, 1))
        expected = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest())
        if not headers.startswith(b"HTTP/1.1 101") or expected not in headers:
            raise ProtocolError("go-judge websocket handshake rejected")
        limits = self.config["limits"]
        command = {
            "args": [
                "/usr/bin/prlimit",
                f"--fsize={limits['file_kb'] * 1024}:{limits['file_kb'] * 1024}",
                "--",
                PYTHON,
                "-I",
                "-B",
                "script.py",
            ],
            "env": ["HOME=/tmp", "LANG=C.UTF-8"],
            "files": [{"streamIn": True}, {"streamOut": True}, {"streamOut": True}],
            "copyIn": {"script.py": {"content": self.config["script"]}},
            "cpuLimit": int((limits["cpu"] + limits["cpu_extra"]) * 1e9),
            "clockLimit": int(limits["wall"] * 1e9),
            "memoryLimit": limits["memory_kb"] * 1024,
            "stackLimit": limits["stack_kb"] * 1024,
            "procLimit": limits["processes"],
        }
        self._send_ws(b"\x01" + json.dumps({"cmd": [command]}).encode())
        emit_stage("go_stream_start", started)

    def _send_ws(self, payload, opcode=2):
        mask = os.urandom(4)
        length = len(payload)
        header = bytes([0x80 | opcode])
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.socket.sendall(header + mask + masked)

    def _recv_ws(self, deadline):
        self.socket.settimeout(max(0.001, deadline - time.monotonic()))
        first, second = read_exact(self.socket, 2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", read_exact(self.socket, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", read_exact(self.socket, 8))[0]
        if length > MAX_PROTOCOL_BYTES:
            raise ProtocolError("go-judge stream packet too large")
        mask = read_exact(self.socket, 4) if second & 0x80 else None
        payload = read_exact(self.socket, length)
        if mask:
            payload = bytes(
                value ^ mask[index % 4] for index, value in enumerate(payload)
            )
        if opcode == 9:
            self._send_ws(payload, opcode=10)
            return self._recv_ws(deadline)
        if opcode == 8:
            return None
        if opcode != 2:
            raise ProtocolError("unexpected go-judge websocket frame")
        return payload

    def send_case(self, index, value, limit):
        packet = (
            json.dumps(
                {"index": index, "input": value, "output_limit_bytes": limit},
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        self._send_ws(b"\x03\x00" + packet)

    def read_chunk(self, deadline):
        while self.response is None:
            packet = self._recv_ws(deadline)
            if packet is None:
                return None
            if len(packet) < 2:
                raise ProtocolError("short go-judge stream packet")
            if packet[0] == 1:
                self.response = json.loads(packet[1:])
                return None
            if packet[0] != 2:
                raise ProtocolError("unknown go-judge stream packet")
            channel, content = packet[1], packet[2:]
            if channel in (1, 16):
                return content
            if channel in (2, 32):
                self.stderr_bytes += len(content)
                self.stderr_overflow |= self.stderr_bytes > 65536
                continue
            raise ProtocolError("unexpected go-judge output channel")
        return None

    def finish(self, deadline):
        while self.response is None:
            if self.read_chunk(deadline) is not None:
                raise ProtocolError("output after expected cases")
        results = (
            self.response.get("results") if isinstance(self.response, dict) else None
        )
        if not isinstance(results, list) or len(results) != 1:
            raise ProtocolError("invalid go-judge stream result")
        report = results[0]
        state = report.get("status")
        termination = (
            "complete"
            if state == "Accepted"
            else "timeout"
            if state == "Time Limit Exceeded"
            else "memory"
            if state == "Memory Limit Exceeded"
            else "output"
            if state == "Output Limit Exceeded"
            else "fatal"
            if state in {"Nonzero Exit Status", "Signalled", "Dangerous Syscall"}
            else "unknown"
        )
        if self.stderr_overflow:
            termination = "output"
        return {
            "termination": termination,
            "time": report.get("time", 0) / 1e9,
            "memory": (report.get("memory", 0) + 1023) // 1024,
        }

    def close(self):
        if self.socket:
            self.socket.close()


def validate_frame(line, index, output_limit):
    try:
        frame = json.loads(line)
    except (ValueError, UnicodeError) as error:
        raise ProtocolError("invalid shared Python case frame") from error
    if not isinstance(frame, dict) or frame.get("index") != index:
        raise ProtocolError("shared Python case index mismatch")
    for name in ("stdout", "stderr"):
        if not isinstance(frame.get(name), str):
            raise ProtocolError("invalid shared Python output")
        if len(frame[name].encode()) > output_limit:
            raise ProtocolError("shared Python output exceeded case bound")
    if frame.get("exception") is not None and not isinstance(frame["exception"], str):
        raise ProtocolError("invalid shared Python exception")
    if not isinstance(frame.get("output_exceeded"), bool):
        raise ProtocolError("invalid shared Python output flag")
    return frame


def run(config):
    session = None
    started = time.monotonic()
    deadline = started + config["limits"]["wall"] + 5
    completed = 0
    termination = {"termination": "unknown", "time": None, "memory": None}
    try:
        session = (
            GoStreamSession(config)
            if config["engine"] == "go-judge"
            else IsolateSession(config)
        )
        reader = FrameReader(session)
        for index, case in enumerate(config["cases"]):
            emit({"type": "start", "index": index})
            if sys.stdin.readline().strip() != "ack":
                raise ProtocolError("parent did not acknowledge case start")
            session.send_case(index, case["input"], case["output_limit_bytes"])
            line = reader.read_line(deadline)
            if line is None:
                break
            frame = validate_frame(line, index, case["output_limit_bytes"])
            emit({"type": "case", "frame": frame})
            if sys.stdin.readline().strip() != "ack":
                raise ProtocolError("parent did not acknowledge case result")
            completed += 1
        extra = reader.read_line(deadline)
        if extra is not None:
            raise ProtocolError("extra shared Python output")
        termination = session.finish(deadline)
        if (
            completed != len(config["cases"])
            and termination["termination"] == "complete"
        ):
            termination["termination"] = "fatal"
    except TimeoutError:
        termination["termination"] = "timeout"
    except (ProtocolError, OSError, EOFError, ValueError, KeyError, TypeError) as error:
        emit({"type": "coordinator_error", "error_class": type(error).__name__})
    finally:
        if session:
            try:
                session.close()
            except (OSError, subprocess.SubprocessError):
                termination["termination"] = "unknown"
    emit(
        {
            "type": "finish",
            "completed_cases": completed,
            "wall_seconds": time.monotonic() - started,
            **termination,
        }
    )


def main():
    line = sys.stdin.readline(8 * 1024 * 1024)
    config = json.loads(line)
    if config["engine"] not in {"isolate", "go-judge"}:
        raise ValueError("unsupported shared Python engine")
    if not 1 <= len(config["cases"]) <= 256:
        raise ValueError("invalid shared Python case count")
    run(config)


if __name__ == "__main__":
    main()
