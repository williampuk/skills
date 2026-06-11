# Manual YouTube transcript retrieval workflow

Use this when `scripts/fetch_youtube_content.py` cannot be run.

## Normalize the ID

Accept these formats:

```text
https://www.youtube.com/watch?v=VIDEO_ID
https://youtu.be/VIDEO_ID
https://www.youtube.com/shorts/VIDEO_ID
https://www.youtube.com/embed/VIDEO_ID
VIDEO_ID
```

## Create a workspace

```bash
VIDEO_ID="1NngTUYPdpI"
URL="https://www.youtube.com/watch?v=${VIDEO_ID}"
OUT="/tmp/youtube_content_${VIDEO_ID}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT/raw"
```

## Direct page fetch

```bash
curl -L --compressed -A 'Mozilla/5.0' "$URL" -o "$OUT/raw/youtube_watch.html"
grep -o 'captionTracks.*' "$OUT/raw/youtube_watch.html" | head
```

## yt-dlp attempts

```bash
yt-dlp --write-auto-subs --skip-download "$URL" -o "$OUT/raw/yt_video" 2>&1 | tee "$OUT/raw/yt_dlp_auto.log"
yt-dlp --write-subs --skip-download --sub-lang en "$URL" -o "$OUT/raw/yt_video" 2>&1 | tee "$OUT/raw/yt_dlp_manual.log"
```

Convert `.vtt` files by removing timestamps and tags.

## youtube-dl fallback

```bash
youtube-dl --write-auto-sub --skip-download "$URL" -o "$OUT/raw/yt_video" 2>&1 | tee "$OUT/raw/youtube_dl_auto.log"
```

## Direct timedtext

Try:

```bash
curl -L "https://www.youtube.com/api/timedtext?v=${VIDEO_ID}&lang=en" -o "$OUT/raw/timedtext_en.xml"
curl -L "https://www.youtube.com/api/timedtext?v=${VIDEO_ID}&lang=en&fmt=vtt" -o "$OUT/raw/timedtext_en.vtt"
curl -L "https://www.youtube.com/api/timedtext?v=${VIDEO_ID}&lang=en&kind=asr&fmt=vtt" -o "$OUT/raw/timedtext_en_asr.vtt"
```

## Metadata APIs

```bash
curl -L "https://noembed.com/embed?url=${URL}" -o "$OUT/raw/noembed.json"
curl -L "https://www.youtube.com/oembed?url=${URL}&format=json" -o "$OUT/raw/oembed.json"
```

## Piped discovery

For a Piped instance:

```bash
curl -L "https://piped.video/api/v1/streams/${VIDEO_ID}" -o "$OUT/raw/piped_streams.json"
```

Inspect `.subtitles[]`. Fetch the best English subtitle URL. A Piped subtitle URL may itself point at, or proxy, YouTube timedtext captions.

## Local media fallback

Look near the MP4 for sidecar subtitles:

```bash
ls -la /path/to/video* | grep -E '\.(vtt|srt|ttml|srv[123]|json)$'
```

Inspect embedded streams:

```bash
ffprobe -hide_banner -i /path/to/video.mp4
```

If no transcript exists and the user has permission, use installed ASR tooling, such as Whisper, but do not install large dependencies without asking.


## Optional fallback: local ASR with faster-whisper

Use this when ordinary caption retrieval does not work, when the user supplied a local MP4/audio file, or when the user wants a transcript independent of YouTube's caption service.

Recommended synchronous command:

```bash
python3 scripts/local_asr_faster_whisper.py "/path/to/video.mp4" --model small --device cpu --compute-type int8 --extract-wav
```

Main-helper integrated command:

```bash
python3 scripts/fetch_youtube_content.py "https://www.youtube.com/watch?v=<id>" --local-media "/path/to/video.mp4" --allow-local-asr --asr-model small
```

Notes:

- `faster-whisper` must already be installed, or the user must explicitly approve installing it and downloading model weights.
- CPU `int8` with the `small` model is a practical default. Use `tiny`/`base` for speed, `medium`/`large-v3` for better accuracy, and CUDA options only when GPU support is available.
- ASR can mishear names, code terms, acronyms, and technical vocabulary. Prefer official/manual captions when they exist.
- Save the JSON segments as evidence for timestamps and later correction.
- Do not represent ASR text as official YouTube captions. Label it clearly as local ASR.
- Avoid `nohup`/background jobs for interactive analysis unless the user explicitly asked to launch a job and inspect the log later.
