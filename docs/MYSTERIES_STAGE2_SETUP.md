# Mysteries of the World — Stage 2 on Windows

This draft feature branch adds **local Kokoro ONNX** narration (British male
\`bm_george\`), one WAV narration file, and a sample-count-derived timing
manifest used to keep long documentary chapters synced. All videos exported
by this branch have **no watermark**. Keep the repository LICENSE file.

## 1. Back up desktop changes before changing Git branches

These instructions assume the Stage 1 checkout at
\`C:\Users\tkkar\Projects\mysteries-youtube-studio\`.

In PowerShell:

\`\`\`powershell
cd "C:\Users\tkkar\Projects\mysteries-youtube-studio"
git status --short
git diff -- video/creator.py config.py > "$HOME\Desktop\mysteries-local-changes.patch"
\`\`\`

If Git reports local modifications to tracked files, **do not use** a forced
checkout or reset. Commit your desktop changes on a separate backup branch,
or safely stash them before switching to the feature branch:

\`\`\`powershell
git stash push -m "desktop changes before stage2" -- video/creator.py config.py
git fetch origin
git switch --track origin/feature/mysteries-documentary-script-engine
\`\`\`

If the new branch has already been created locally, use
\`git switch feature/mysteries-documentary-script-engine\` instead.

> This branch already excludes the watermark. Do not blindly \`git stash pop\`
> over it: that may restore the old watermark code or cause conflicts.

## 2. Install optional Kokoro dependencies

\`\`\`powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-documentary.txt
\`\`\`

## 3. Download the official open model assets (once)

\`\`\`powershell
New-Item -ItemType Directory -Force "models\kokoro" | Out-Null
curl.exe -fL --retry 2 -o "models\kokoro\kokoro-v1.0.onnx" "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
curl.exe -fL --retry 2 -o "models\kokoro\voices-v1.0.bin" "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"
\`\`\`

Model files are ignored by Git; never add them to a commit. This is a
subscription-free local TTS integration. The default speech settings in
\`config.py\` use \`bm_george\` with \`KOKORO_SPEED = 0.92\`. Exact speech duration
depends on the text and the chosen speed.

## 4. Run the offline test suite

\`\`\`powershell
.\.venv\Scripts\python.exe -m pytest -q
\`\`\`

## 5. Try a controlled documentary narration

Start with a reviewed 10-minute Bermuda Triangle **script**, not an hour-long
render. In the GUI, you can run the research and script stages first. Read the
result in \`output\script.json\` before running narration.

When the script is ready, select Narration (and optionally Video). Outputs:

- \`output\narration.wav\`: full Kokoro narration
- \`output\narration_timing.json\`: measured chapter times
- \`output\final_video.mp4\`: video with chapters matched to speech

Kokoro provides waveform audio but not word-level timecodes. Therefore this
stage does not generate false "accurate" captions. True word-aligned subtitles
will be a later enhancement.

The voice and renderer are **not yet validated on your Windows desktop**.
Review audio, visuals, factual claims, and media permissions before publishing.
Video assembly at 1080p/24 fps is still resource-intensive for 60–90 minutes.

**Do not connect or publish to YouTube while evaluating this stage.**
