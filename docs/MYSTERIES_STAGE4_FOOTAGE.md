# Stage 4 — Footage discovery prototype (90-second Bermuda Triangle preview)

This is the **first working component** of our video-led documentary production
upgrade, not a finished video editor. The existing YAAS Visuals step, narration,
video exports and settings remain unchanged.

## What it does

- Reads the **existing** output/script.json and output/narration_timing.json.
- Verifies that the chapter timing metadata matches the *current* script.
- Plans short visual slots for the first 90 seconds without cutting across a
  narrated chapter boundary.
- Searches **Pexels Videos** (free API key) and **Wikimedia Commons** (no key).
- Uses a conservative automated Commons license filter: CC0, public domain,
  CC BY and CC BY-SA. Every asset is still **pending human review**.
- Downloads only the selected media files when explicitly requested.
- Writes output/footage/preview_manifest.json with source URL, page URL, author,
  license, intended scene, exact slot and download status.
- Never rewrites the script, narration.wav, chapter timing, images or MP4.

## Run on Windows PowerShell

From the repository directory, first update your feature branch:

    git pull --ff-only

Run existing tests plus the new footage tests:

    .\.venv\Scripts\python.exe -m pytest -q

Make sure you previously generated your full chapter narration and that
output/script.json matches output/narration_timing.json. Then run:

    .\.venv\Scripts\python.exe footage_preview.py --plan-only

This is an **offline test**. It generates a shot plan and makes zero API calls.

To search for eligible candidate media online (without downloading it):

    .\.venv\Scripts\python.exe footage_preview.py

To download candidate source files for **manual visual/licence review**:

    .\.venv\Scripts\python.exe footage_preview.py --download

Media is saved to output/footage/shot_01.mp4 etc (Commons may return .webm,
.jpg, or .png); browse the folder with:

    explorer .\output\footage

Each download is capped at 80 MiB. A skipped or failed download will be
reported in preview_manifest.json. If a service is down, it records the error
and tries the other eligible provider. Media may be missing; the tool never
fabricates or silently substitutes unrelated AI images.

## Pexels setup (optional)

In YAAS Settings, enter your Pexels API key. It is stored in the local .env
file, NOT in this repository. If you leave the key blank, the preview uses
Wikimedia Commons only. See https://www.pexels.com/api/.

Pexels asks API consumers to provide a prominent link to Pexels and credit
photographers where possible. The manifest retains that information for the
eventual description/credits page. Relevant sources:

- Pexels API: https://www.pexels.com/api/documentation/
- Pexels License: https://www.pexels.com/license
- Wikimedia Commons: https://commons.wikimedia.org/
- Reusing Commons content: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia

## What must be checked before publication

- **Source accuracy:** generic ocean B-roll is illustrative, not genuine
  footage of USS Cyclops or Flight 19.
- **Licenses:** verify every file's Commons file page, original creator,
  CC version, any share-alike conditions, third-party rights and attribution.
  Catalogue labels are not legal clearance.
- **Visual relevance:** check every clip's subject, orientation, resolution
  and intended passage of narration.
- **Privacy/trademarks:** stock licences do not automatically clear a
  depicted person's image or an unrelated brand's marks.
- **Media quality:** this stage does not normalize framerates or verify clip
  playback; that belongs in the FFmpeg editing stage.

## Next coding task

Use this manifest as input for a basic **FFmpeg preview renderer** that
trims/loops downloaded footage to the narrated time slots, animates still
images, preserves narration audio, exports 1080p MP4 and reports gaps. Build
review and quality checks before connecting that workflow to the YAAS GUI.

No uploads or publishing are part of this prototype.
