---
name: video-transcriber
description: Use this skill when the user gives a local video/audio file, a YouTube URL/video ID, or another web video link and asks to transcribe, subtitle, summarize, or analyze spoken video content. For local media, use Python and faster-whisper directly. For web video links, first try transcript/caption resources without downloading the video; if those fail, download the video to the workspace tmp/videos folder with yt-dlp, then transcribe the downloaded local file.
---

# Video Transcriber

This skill retrieves or creates transcripts from local media files and web video links.

Use it when the user asks for any of the following:

- transcribe a local video/audio file
- summarize or analyze a YouTube video
- get YouTube subtitles, captions, ASR captions, or timedtext
- extract chapters, timestamps, examples, code, quotes, or topics from a video
- download a web video only because transcript/caption resources failed and local ASR is needed

## Core principle

Follow the source-specific ladder. Do not improvise a new one-off approach every time.

1. **Local media file**: transcribe directly with `scripts/local_asr_faster_whisper.py`.
2. **Web video link**: try transcript/caption resources first with `scripts/fetch_youtube_content.py`.
3. **Fallback for web video**: only if transcript resources fail, download the video with `yt-dlp` into the workspace `tmp/videos/` folder, then run local ASR on that downloaded file.

Respect access controls and copyright. Do not bypass paywalls, private video restrictions, account-only access, DRM, or age-gated/login-only content. Prefer summaries and user-directed analysis. Only provide long verbatim transcript text when the user owns the video, has supplied the transcript/media themselves, or reuse is clearly permitted.

Never print cookie file contents. If cookies are needed, the human/user should provision the cookie file path in the `YTDLP_COOKIES_FILE` environment variable; see `references/COOKIES.md`.

## Workspace layout

Default to a workspace-local `tmp` directory unless the user specifies another location:

```text
tmp/
  videos/       # downloaded video/audio fallback files
  transcripts/  # transcript run outputs
  raw/          # optional raw logs/caption files
```

Downloaded web videos must go under:

```text
tmp/videos/
```

## Case 1: local video/audio file

If the input is already a local file, do not use web download tools. Run local ASR directly:

```bash
mkdir -p tmp/transcripts
python3 scripts/local_asr_faster_whisper.py "<local-media-file>" \
  --out-dir "tmp/transcripts/<safe-run-name>" \
  --model small \
  --device cpu \
  --compute-type int8
```

Use stronger settings when the user wants accuracy and runtime is acceptable:

```bash
python3 scripts/local_asr_faster_whisper.py "<local-media-file>" \
  --out-dir "tmp/transcripts/<safe-run-name>" \
  --model medium \
  --device cpu \
  --compute-type int8
```

For CUDA-capable environments:

```bash
python3 scripts/local_asr_faster_whisper.py "<local-media-file>" \
  --out-dir "tmp/transcripts/<safe-run-name>" \
  --model large-v3 \
  --device cuda \
  --compute-type float16
```

After transcription, read:

```text
tmp/transcripts/<safe-run-name>/local_asr_report.md
tmp/transcripts/<safe-run-name>/local_asr_transcript.txt
tmp/transcripts/<safe-run-name>/local_asr_transcript.json
```

## Case 2: web video link

For a YouTube URL/video ID or web video URL, first try transcript/caption resources without downloading the video:

```bash
mkdir -p tmp/transcripts tmp/raw
python3 scripts/fetch_youtube_content.py "<youtube-url-or-video-id>" \
  --out-dir "tmp/transcripts/<safe-run-name>"
```

The helper tries the existing retrieval ladder:

1. normalize YouTube ID
2. direct YouTube watch page fetch
3. `captionTracks` extraction
4. `yt-dlp --write-subs/--write-auto-subs --skip-download`
5. `youtube-dl` subtitle fallback when available
6. direct YouTube timedtext variants
7. metadata APIs such as noembed/oEmbed
8. Piped frontend subtitle discovery
9. local sidecar subtitles when local media is also supplied
10. optional local ASR only when explicitly requested with a local media file

If `transcript.txt` exists after this step, stop. Use that transcript and do not download the video.

Read:

```text
tmp/transcripts/<safe-run-name>/report.md
tmp/transcripts/<safe-run-name>/metadata.json
tmp/transcripts/<safe-run-name>/transcript.txt
```

## Case 3: web transcript resources failed, download fallback

Only after web transcript/caption resources fail, download the video into `tmp/videos/`.

First check whether the cookie-file environment variable is set:

```bash
if [ -n "${YTDLP_COOKIES_FILE:-}" ]; then
  YTDLP_COOKIE_ARGS=(--cookies "$YTDLP_COOKIES_FILE")
else
  YTDLP_COOKIE_ARGS=()
fi
```

Then check JavaScript runtime support for yt-dlp's YouTube EJS challenge solving. Deno is preferred and is enabled by yt-dlp by default. If Deno is not available but Node or QuickJS is available, explicitly enable it:

```bash
YTDLP_JS_ARGS=()
if command -v deno >/dev/null 2>&1; then
  :  # Deno is enabled by default; no extra arg needed.
elif command -v node >/dev/null 2>&1; then
  YTDLP_JS_ARGS=(--js-runtimes node)
elif command -v qjs >/dev/null 2>&1; then
  YTDLP_JS_ARGS=(--js-runtimes quickjs)
else
  echo "No supported JavaScript runtime found for yt-dlp EJS challenge solving. Install Deno first, or Node/QuickJS as fallback." >&2
fi
```

Then run `yt-dlp`. If `YTDLP_COOKIES_FILE` is set, the command uses it. If it is not set, the command does not add any cookie option. If Node/QuickJS is needed, the command includes the correct `--js-runtimes` option:

```bash
mkdir -p tmp/videos
yt-dlp "${YTDLP_JS_ARGS[@]}" "${YTDLP_COOKIE_ARGS[@]}" \
  --no-playlist \
  --write-info-json \
  --restrict-filenames \
  -f "best[ext=mp4]/best" \
  -o "tmp/videos/%(title).180B-%(id)s.%(ext)s" \
  "<web-video-url>"
```

Do not ask the user to pass a cookie path directly on the command line. The only supported skill convention is `YTDLP_COOKIES_FILE`.

## yt-dlp EJS / n-challenge troubleshooting

If `yt-dlp --list-formats` shows only storyboard/image formats such as `sb0`, `sb1`, `sb2`, `sb3`, or `mhtml`, and the log says `n challenge solving failed`, do not treat that as a usable video download. It usually means the environment is missing EJS support.

Do this checklist:

```bash
yt-dlp --version
python3 -m pip show yt-dlp yt-dlp-ejs 2>/dev/null || true
command -v deno || true
command -v node || true
command -v qjs || true
yt-dlp --verbose --list-formats "<web-video-url>" 2>&1 | tee tmp/yt-dlp-verbose.log
```

For pip-based installs, install or update yt-dlp with its default dependencies:

```bash
python3 -m pip install -U "yt-dlp[default]"
```

If no JavaScript runtime is available, ask the user to install Deno. If Deno cannot be installed but Node is available, use `--js-runtimes node`. If QuickJS is available as `qjs`, use `--js-runtimes quickjs`.

For more details, see `references/YTDLP_EJS_TROUBLESHOOTING.md`.

Then transcribe the downloaded local video file:

```bash
python3 scripts/local_asr_faster_whisper.py "tmp/videos/<downloaded-file>" \
  --out-dir "tmp/transcripts/<safe-run-name>-local-asr" \
  --model small \
  --device cpu \
  --compute-type int8
```

Label this transcript source as `local ASR/faster-whisper from downloaded video`, not as official YouTube captions.

## Optional integrated local-ASR rerun

For YouTube links, after downloading the media, you may also rerun the existing helper with `--local-media` and `--allow-local-asr` so the final report ties together URL metadata and local ASR:

```bash
python3 scripts/fetch_youtube_content.py "<youtube-url-or-video-id>" \
  --local-media "tmp/videos/<downloaded-file>" \
  --allow-local-asr \
  --asr-model small \
  --asr-device cpu \
  --asr-compute-type int8 \
  --out-dir "tmp/transcripts/<safe-run-name>-combined"
```

## Summarization requirements

When a transcript is available and the user asks for details, provide a structured summary covering, when present:

- title, channel/uploader, duration, upload date, description, and transcript source
- chapters/sections in order, with timestamps if available
- all major topics from beginning to end
- key technical concepts and definitions
- strategies, algorithms, patterns, and tradeoffs
- numerical examples, scenarios, diagrams, slides, code examples, screenshots, or whiteboard content mentioned
- failure modes, caveats, edge cases, and operational challenges
- short memorable quotes within copyright-safe limits
- transcript file path

## Reporting format

When finished, include:

```text
Transcript source: <web captions | yt-dlp subtitles | timedtext | Piped | local ASR/faster-whisper | local ASR/faster-whisper from downloaded video | unavailable>
Transcript saved at: <path or unavailable>
Downloaded video: <path or not needed>
Metadata/report saved at: <path or unavailable>
Methods tried: <short list of successes/failures>
```

Then provide the user-facing summary or transcript.

## Failure handling

If no transcript is found:

- Say clearly that transcript retrieval failed.
- Explain which methods were tried.
- Use available metadata only if available.
- Suggest the user provide a `.vtt`, `.srt`, `.json`, downloaded media file, provision `YTDLP_COOKIES_FILE` when access requires authentication, or install Deno/yt-dlp EJS support when `n challenge solving failed` appears.

Do not hallucinate video content from only the title.