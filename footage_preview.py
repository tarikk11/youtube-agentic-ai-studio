"""Plan and optionally download footage for the first 90 seconds of a documentary.

From the repository root (using YAAS's primary venv):
  .\.venv\Scripts\python.exe footage_preview.py --plan-only
  .\.venv\Scripts\python.exe footage_preview.py
  .\.venv\Scripts\python.exe footage_preview.py --download

No script regeneration, narration synthesis, upload or video rendering occurs.
"""
import argparse
import json

from video.footage import create_preview_manifest


def main():
    parser = argparse.ArgumentParser(description="Documentary footage discovery preview")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--seconds", type=float, default=90)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plan-only", action="store_true",
                       help="Plan shot timings without network access.")
    group.add_argument("--download", action="store_true",
                       help="Download selected source media (max 80 MB per file).")
    args = parser.parse_args()

    try:
        manifest = create_preview_manifest(
            args.output_dir, seconds=args.seconds,
            download=args.download, plan_only=args.plan_only,
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        parser.exit(1, f"Cannot build footage preview: {exc}\n")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    print(f"\nPreview plan saved: {manifest}")
    print(f"Subject: {data['script_title']}")
    print(f"Source acknowledgement: {data['pexels_credit']}")
    for shot in data["shots"]:
        asset = shot.get("asset")
        label = (f"{asset['source']} / {asset['media_type']}"
                 if asset else "no eligible asset found")
        print(f"  {shot['start_seconds']:6.1f}-{shot['end_seconds']:6.1f}s"
              f"  {label}: {shot['query']}")
        for warning in shot.get("warnings", []):
            print(f"    Warning: {warning}")
    if args.plan_only:
        print("\nPlanning only; no network calls or downloads were made.")
    elif args.download:
        print("\nDownloaded media is not cleared for publication. "
              "Inspect each file and licence before using it.")
    else:
        print("\nSearch results only. Re-run with --download to fetch media.")
    print("Your existing script, narration and final video were not changed.")


if __name__ == "__main__":
    main()
