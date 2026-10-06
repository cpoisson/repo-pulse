# repo-pulse video and README GIF

Remotion project (same version as `inside-s2s`). Everything is generated from source:

```bash
cd media/video && npm install
uvx --with playwright python scripts/capture.py          # 2x slide screenshots from the anonymized docs/examples/ decks -> public/slides/
(cd ../.. && uv run python media/video/scripts/music_styles.py --style video --seconds 72 --out media/video/public/music.wav)  # arranged track
npx remotion studio src/index.ts                           # preview
npx remotion render src/index.ts RepoPulse out/repo-pulse.mp4 --codec=h264 --crf=18 --audio-codec=aac
npx remotion render src/index.ts ReadmeGif out/readme.mp4 --codec=h264 --crf=16 --scale=0.5
ffmpeg -y -i out/readme.mp4 -vf "fps=10,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" -loop 0 ../../docs/repo-pulse.gif
```

- `RepoPulse`: 1920×1080, ~71 s, YouTube cut with music. `ReadmeGif`: ~21 s loop, slides held still (smaller GIF).
- Music: `scripts/music_styles.py` synthesizes everything (no samples, no third-party audio), so it is free to publish.
  `--style video` is the final track (synthwave rhythm × future-garage harmony, arranged to the scenes); other styles
  (`lofi`, `launch`, `ambient`, `acoustic`, `electronic`, `elec_*`) are the alternatives that were auditioned.
- Facts shown on screen come from the 2026-10-06 editions in `data/` (lerobot, moshi, speech-to-speech).
