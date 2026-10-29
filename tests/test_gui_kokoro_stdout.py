"""Regression tests for YAAS GUI stdout capture during Kokoro narration."""
import io
import sys
import subprocess

from gui import _Capture
from video.kokoro_narrator import run_kokoro_worker


def test_gui_stdout_capture_exposes_console_encoding():
    original = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    capture = _Capture(original)
    assert capture.encoding == "cp1252"
    assert capture.errors == "strict"
    capture.write("A narration line\\n")
    capture.flush()


def test_kokoro_worker_tolerates_stdout_without_encoding(monkeypatch, tmp_path):
    # Old GUI logger had write/flush but no encoding attribute.
    class LogOnlyStream:
        def __init__(self):
            self.lines = []
        def write(self, value):
            self.lines.append(value)
        def flush(self):
            pass

    class FakePopen:
        stdout = ["   → Narrating chapter 1\\n"]
        def wait(self):
            return 0

    def fake_popen(command, **kwargs):
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8:backslashreplace"
        (tmp_path / "narration.wav").write_bytes(b"RIFFmock")
        return FakePopen()

    monkeypatch.setenv("KOKORO_PYTHON", sys.executable)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    log = LogOnlyStream()
    monkeypatch.setattr(sys, "stdout", log)
    output = run_kokoro_worker({"sections": []}, str(tmp_path))
    assert output.endswith("narration.wav")
    assert "Narrating chapter 1" in "".join(log.lines)
