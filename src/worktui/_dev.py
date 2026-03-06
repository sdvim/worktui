"""Hot-reload dev server. Usage: uv run --group dev dev"""

import os
import signal
import subprocess
import sys

from watchfiles import watch


def main() -> None:
    proc: subprocess.Popen | None = None

    def _start() -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-m", "worktui.app"],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            start_new_session=True,
        )

    def _stop(p: subprocess.Popen) -> None:
        if p.poll() is not None:
            return
        # Send SIGINT first (Textual handles this), fall back to SIGKILL
        try:
            os.killpg(p.pid, signal.SIGINT)
            p.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()

    def _shutdown(*_: object) -> None:
        if proc and proc.poll() is None:
            _stop(proc)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    proc = _start()
    try:
        for _changes in watch("src/worktui", raise_interrupt=False):
            _stop(proc)
            proc = _start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if proc:
            _stop(proc)
