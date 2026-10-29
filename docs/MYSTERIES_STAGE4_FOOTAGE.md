# Stage 4 — Keyless documentary footage prototype

Pexels **paused issuing new API keys** in late 2026. This new documentary
footage preview does **not** call Pexels and does not require any API key.
Legacy YAAS still-image features may still contain a Pexels option for users
with existing keys, but it is irrelevant to this workflow.

## Sources now supported

1. **Wikimedia Commons**, no key: searches for video before falling back to
   still images. Candidate files are filtered to known commercial-use licences
   (CC0, public domain labels, CC BY, CC BY-SA) and flagged for manual review.
2. **Internet Archive**, no key: searches public film records and fetches
   metadata. Candidate clips require an explicit compatible CC licence URL
   and a file no larger than 80 MiB. A licence claimed by an uploader **does
   not prove** rights or historical authenticity. Every file stays pending
   human review.
3. **Pixabay Videos**, optional free key: atmospheric stock footage, queried
   from https://pixabay.com/api/videos/. Our implementation caches each query
   result for 24 hours as the provider requires, avoids mass downloading,
   and tracks original creator/license. Check availability of keys at
   https://pixabay.com/api/docs/ and comply with Pixabay's terms.

The preview prioritizes archive sources for historic scenes, then Commons
and Internet Archive for general scenes when Pixabay is unavailable. It
never uses an unlicensed media result simply to fill a timeline gap.

## Try it on Windows (PowerShell)

With the Stage 2 feature branch checked out, fetch the latest commits:

    git pull --ff-only

Run all automated tests:

    .\.venv\Scripts\python.exe -m pytest -q

Assumes existing matching files at:

- output/script.json
- output/narration.wav
- output/narration_timing.json

First, generate a shot plan **without any web calls**:

    .\.venv\Scripts\python.exe footage_preview.py --plan-only

Next, try **keyless online search without downloads**:

    .\.venv\Scripts\python.exe footage_preview.py

To download shortlisted files for rights/visual inspection:

    .\.venv\Scripts\python.exe footage_preview.py --download

View the manifest and files:

    notepad .\output\footage\preview_manifest.json
    explorer .\output\footage

The manifest includes shot timing, the source, file link, file page, creator,
claimed licence, and any provider errors. A missing clip is explicitly marked
missing. A source may decline or rate-limit requests; this is logged, and the
next provider is attempted. Downloads occur only with --download and have an
80 MiB file-size cap.

## Important limitations

- This is **media discovery, not video rendering**. The existing YAAS
  Visuals button is separate and has not been replaced yet.
- Internet Archive search results are sometimes sparse, unreliable or too
  big for the preview. Not every item is downloadable/reusable.
- Commons and Archive catalogue metadata are insufficient for legal
  clearance. Check rights and creator attribution on each original item page.
- Any generic stock ocean footage must be identified as an illustration,
  never as a genuine recording of USS Cyclops, Flight 19 or another event.
- Manual review is still required for media suitability, licence conditions,
  people/trademarks, image quality and soundtrack contamination.
- Pixabay forbids systematic mass downloads and requires 24h API caching;
  this preview makes a few deliberate searches, not broad harvesting.

## Next milestone

After keyless sourcing works on the user's Windows machine, add a separate
FFmpeg **90-second narrated preview renderer**, initially with manual
shot approval. Reuse source assets, timing and narration already on disk.
Do not alter the main YAAS video workflow or upload anything to YouTube.

Official references:

- Pexels key notice: https://help.pexels.com/hc/en-us/articles/900004904026-How-do-I-get-an-API-key
- Wikimedia Commons reuse: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
- Wikimedia file metadata API: https://www.mediawiki.org/wiki/API:Imageinfo
- Internet Archive API: https://archive.org/services/docs/api/
- Pixabay Videos API and caching: https://pixabay.com/api/docs/
