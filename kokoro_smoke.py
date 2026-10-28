"""Smoke test the downloaded local Kokoro bm_george model on this desktop.

Run from the repository folder:
    .\.venv\Scripts\python.exe kokoro_smoke.py

Creates a short WAV in output/kokoro-smoke. No internet/API key required.
"""
from pathlib import Path

from video.kokoro_narrator import run_kokoro_worker


def main():
    script = {
        "style": "sleep_documentary",
        "sections": [
            {
                "id": 1,
                "title": "A Quiet Ocean",
                "narration": (
                    "Far beyond the shoreline, the Atlantic Ocean stretches "
                    "toward the horizon. For centuries, sailors travelled "
                    "these waters, guided by the stars, the wind, and the "
                    "careful observations recorded in their journals."
                ),
            },
            {
                "id": 2,
                "title": "Stories on the Water",
                "narration": (
                    "Some voyages became the subjects of legends. "
                    "Yet behind every familiar mystery lies a quieter "
                    "question: what do the surviving records actually tell us?"
                ),
            },
        ],
    }
    folder = Path("output") / "kokoro-smoke"
    path = run_kokoro_worker(script, str(folder))
    print(f"\nListen to the generated voice: {Path(path).resolve()}")
    print(f"Timing metadata: {(folder / 'narration_timing.json').resolve()}")


if __name__ == "__main__":
    main()
