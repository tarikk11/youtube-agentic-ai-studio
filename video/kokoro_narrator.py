"""Offline Kokoro ONNX narration with sample-accurate chapter boundaries.

The narrator writes WAV incrementally (low memory for long episodes), saves
chapter start/end times from actual PCM sample counts, and avoids simulated
word-level caption timestamps. Generated media/model files must stay local.
"""
import hashlib
import json
import os
import re
from pathlib import Path

import config

MAX_CHARS = 260
DEFAULT_CHUNK_PAUSE = 0.16
DEFAULT_CHAPTER_PAUSE = 0.85


def script_hash(script: dict) -> str:
    """Fingerprint all section ids and text to reject stale timing metadata."""
    payload = [(s["id"], s.get("narration", "")) for s in script.get("sections", [])]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def split_for_kokoro(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split on sentence boundaries and then whitespace, avoiding long requests."""
    if max_chars < 40:
        raise ValueError("max_chars must be at least 40.")
    sentences = re.split(r"(?<=[.!?…])\s+|\n+", text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        sentence = " ".join(sentence.split())
        if not sentence:
            continue
        # A single sentence can exceed Kokoro's phoneme limit: split at words.
        for word in sentence.split():
            if len(word) > max_chars:
                raise ValueError(f"Unusually long unbreakable word ({len(word)} chars).")
            new = f"{current} {word}".strip()
            if len(new) > max_chars:
                if current:
                    chunks.append(current)
                current = word
            else:
                current = new
    if current:
        chunks.append(current)
    return chunks


def model_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parent.parent
    directory = root / "models" / "kokoro"
    model = Path(getattr(config, "KOKORO_MODEL_PATH", str(directory / "kokoro-v1.0.onnx")))
    voices = Path(getattr(config, "KOKORO_VOICES_PATH", str(directory / "voices-v1.0.bin")))
    return model, voices


def generate_documentary_narration(script: dict, output_dir: str) -> str:
    """Synthesize independently, preserving full audiobook audio and chapter spans.

    Requires the optional kokoro-onnx and soundfile packages and local model files.
    Outputs narration.wav and narration_timing.json. No false SRT timings are
    generated: subtitles can be added with speech alignment in a later stage.
    """
    try:
        import numpy as np
        import soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        raise RuntimeError(
            "Kokoro voice-worker dependencies are missing from .venv-kokoro. "
            "Install them using: .\\.venv-kokoro\\Scripts\\python.exe "
            "-m pip install -r requirements-documentary.txt "
            "(do not install them into the main .venv)."
        ) from exc

    model, voices = model_paths()
    if not model.is_file() or not voices.is_file():
        raise FileNotFoundError(
            f"Kokoro model files missing. Put kokoro-v1.0.onnx and "
            f"voices-v1.0.bin in {model.parent}, or configure KOKORO_MODEL_PATH "
            f"and KOKORO_VOICES_PATH. Missing: "
            f"{[str(p) for p in (model, voices) if not p.is_file()]}"
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    audio_path = output / "narration.wav"
    temp_audio = output / "narration.partial.wav"
    timing_path = output / "narration_timing.json"
    # Remove stale metadata and Edge caption data before synthesising.
    timing_path.unlink(missing_ok=True)
    (output / "narration.srt").unlink(missing_ok=True)
    temp_audio.unlink(missing_ok=True)

    voice_name = getattr(config, "KOKORO_VOICE", "bm_george")
    speed = float(getattr(config, "KOKORO_SPEED", 0.92))
    if not 0.5 <= speed <= 2.0:
        raise ValueError("KOKORO_SPEED must be in the range 0.5 to 2.0.")
    chapter_pause = float(getattr(config, "KOKORO_CHAPTER_PAUSE", DEFAULT_CHAPTER_PAUSE))
    chunk_pause = float(getattr(config, "KOKORO_CHUNK_PAUSE", DEFAULT_CHUNK_PAUSE))
    if min(chapter_pause, chunk_pause) < 0:
        raise ValueError("Kokoro pauses must be non-negative.")

    engine = Kokoro(str(model), str(voices))
    available = engine.get_voices()
    if voice_name not in available:
        raise ValueError(f"Voice {voice_name!r} is not in Kokoro model voice list.")

    print(f"   -> Narrating documentary locally with Kokoro {voice_name} at {speed:.2f}x")
    sample_rate = None
    written_samples = 0
    spans = []
    wav_file = None
    try:
        for section_index, section in enumerate(script["sections"]):
            text = (section.get("narration") or "").strip()
            chunks = split_for_kokoro(text)
            if not chunks:
                raise ValueError(f"Chapter {section.get('id')} has no narration.")
            start_samples = written_samples
            for i, chunk in enumerate(chunks):
                samples, rate = engine.create(
                    chunk, voice=voice_name, speed=speed, lang="en-gb"
                )
                rate = int(rate)
                if wav_file is None:
                    sample_rate = rate
                    wav_file = sf.SoundFile(str(temp_audio), mode="w",
                                            samplerate=sample_rate, channels=1,
                                            format="WAV", subtype="PCM_16")
                if rate != sample_rate:
                    raise ValueError("Kokoro sample rate changed between chunks.")
                samples = np.asarray(samples, dtype=np.float32).reshape(-1)
                if not len(samples) or not np.all(np.isfinite(samples)):
                    raise ValueError(f"Invalid audio samples in chapter {section['id']}.")
                wav_file.write(samples)
                written_samples += len(samples)
                if i < len(chunks) - 1 and chunk_pause:
                    pause_count = round(chunk_pause * sample_rate)
                    wav_file.write(np.zeros(pause_count, dtype=np.float32))
                    written_samples += pause_count

            if section_index < len(script["sections"]) - 1 and chapter_pause:
                pause_count = round(chapter_pause * sample_rate)
                wav_file.write(np.zeros(pause_count, dtype=np.float32))
                written_samples += pause_count

            start = start_samples / sample_rate
            end = written_samples / sample_rate
            spans.append({
                "id": section["id"],
                "title": section.get("title", ""),
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "duration_seconds": round(end - start, 6),
            })
            print(f"      Chapter {section_index + 1}: {end - start:.1f}s "
                  f"({len(chunks)} chunks)")
    finally:
        if wav_file is not None:
            wav_file.close()
        # Most Kokoro builds expose a closable voice archive. Don't mask
        # synthesis failures if a particular version lacks that method.
        close = getattr(getattr(engine, "voices", None), "close", None)
        if callable(close):
            close()

    if sample_rate is None:
        raise ValueError("No narration audio was generated.")
    os.replace(temp_audio, audio_path)

    metadata = {
        "version": 1,
        "source_audio": audio_path.name,
        "voice": voice_name,
        "sample_rate": sample_rate,
        "total_duration_seconds": round(written_samples / sample_rate, 6),
        "script_hash": script_hash(script),
        "sections": spans,
    }
    # Writing this last marks the narration as complete.
    timing_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"   -> Audio: {audio_path} ({metadata['total_duration_seconds']:.1f}s)")
    print(f"   -> Exact chapter timeline: {timing_path}")
    return str(audio_path)


def load_chapter_timing(script: dict, output_dir: str, audio_duration: float) -> list[dict]:
    """Validate a complete matching timeline; refuse to shorten speech silently."""
    path = Path(output_dir) / "narration_timing.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Documentary chapter timing missing: {path}. Re-run the Narration step."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("script_hash") != script_hash(script):
        raise ValueError("Narration timing belongs to a different script. "
                         "Re-run the Narration step.")
    spans = data.get("sections", [])
    if not spans or len(spans) != len(script.get("sections", [])):
        raise ValueError("Narration chapter count does not match the current script.")
    previous_end = 0.0
    for section, span in zip(script["sections"], spans):
        if section["id"] != span.get("id"):
            raise ValueError("Narration chapter IDs do not match the current script.")
        if (abs(span["start_seconds"] - previous_end) > 0.01
                or span["end_seconds"] <= span["start_seconds"]):
            raise ValueError("Narration contains invalid or overlapping chapter boundaries.")
        previous_end = span["end_seconds"]

    if abs(previous_end - audio_duration) > 0.35:
        raise ValueError(
            f"Audio length ({audio_duration:.2f}s) does not match recorded chapter "
            f"timeline ({previous_end:.2f}s). Check your mixed audio and re-run."
        )
    return spans


def run_kokoro_worker(script: dict, output_dir: str) -> str:
    """Run Kokoro in its own virtualenv so NumPy 2 never breaks MoviePy 1."""
    import subprocess
    import tempfile

    root = Path(__file__).resolve().parent.parent
    executable = os.getenv("KOKORO_PYTHON")
    if not executable:
        executable = str(root / ".venv-kokoro"
                         / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    if not Path(executable).is_file():
        raise FileNotFoundError(
            f"Separate Kokoro Python environment not found at {executable}. "
            "Create .venv-kokoro and install requirements-documentary.txt "
            "(see docs/MYSTERIES_STAGE2_SETUP.md)."
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", prefix="kokoro-script-",
            dir=str(output), delete=False
        ) as handle:
            json.dump(script, handle, ensure_ascii=False)
            tmp_path = handle.name

        command = [
            executable, "-m", "video.kokoro_narrator", "--script", tmp_path,
            "--output-dir", str(output.resolve())
        ]
        # Some Windows consoles use cp1252. Keep worker output UTF-8
        # and escape characters unprintable by the parent console.
        worker_env = os.environ.copy()
        worker_env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
        process = subprocess.Popen(
            command, cwd=str(root), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            encoding="utf-8", errors="replace", env=worker_env,
        )
        if process.stdout:
            import sys
            encoding = sys.stdout.encoding or "utf-8"
            for line in process.stdout:
                safe = line.rstrip().encode(encoding, errors="backslashreplace").decode(encoding)
                print(safe)
        code = process.wait()
        if code:
            raise RuntimeError(f"Kokoro voice worker exited with code {code}; "
                               "see earlier narration output for the cause.")
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    audio = output / "narration.wav"
    if not audio.is_file():
        raise FileNotFoundError(
            f"Kokoro worker ended without producing the expected WAV: {audio}"
        )
    return str(audio)


def _main() -> None:
    """CLI entry used by the isolated interpreter only."""
    import argparse
    parser = argparse.ArgumentParser(description="Isolated Kokoro documentary TTS worker")
    parser.add_argument("--script", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source = json.loads(Path(args.script).read_text(encoding="utf-8"))
    generate_documentary_narration(source, args.output_dir)


if __name__ == "__main__":
    _main()
