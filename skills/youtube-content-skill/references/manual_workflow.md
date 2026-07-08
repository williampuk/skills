# Manual Video Transcriber Workflow

Use this when the helper scripts cannot be run directly or when you need to reason through the workflow step by step.

## Decision tree

```text
Input is a local media file?
  -> transcribe directly with local ASR

Input is a web video link?
  -> try transcript/caption resources first
  -> if transcript is found, stop
  -> if transcript is unavailable, download video to tmp/videos
  -> transcribe downloaded local video with local ASR
```

## Local media workflow

For `.mp4`, `.mkv`, `.mov`, `.webm`, `.mp3`, `.m4a`, `.wav`, etc.:

```bash
mkdir -p tmp/transcripts/local_media
python3 scripts/local_asr_faster_whisper.py "/path/to/video.mp4" \
  --out-dir tmp/transcripts/local_media \
  --model small \
  --device cpu \
  --compute-type int8
```

Useful output files:

```text
tmp/transcripts/local_media/local_asr_report.md
tmp/transcripts/local_media/local_asr_transcript.txt
tmp/transcripts/local_media/local_asr_transcript.srt
tmp/transcripts/local_media/local_asr_transcript.json
```

## Web video transcript-first workflow

For YouTube links, YouTube IDs, and similar web video links, do not download the video first. Try transcript resources first.

```bash
VIDEO_URL="https://www.youtube.com/watch?v=VIDEO_ID"
OUT="tmp/transcripts/VIDEO_ID"
mkdir -p "$OUT" tmp/videos
python3 scripts/fetch_youtube_content.py "$VIDEO_URL" --out-dir "$OUT"
```

Inspect:

```bash
cat "$OUT/report.md"
ls -la "$OUT"
```

If this exists, use it and stop:

```text
$OUT/transcript.txt
```

## What the transcript-first helper tries

The existing helper tries, in order:

1. normalize the YouTube video ID
2. direct YouTube watch page fetch
3. `captionTracks` extraction from the player response
4. `yt-dlp --write-subs --skip-download`
5. `yt-dlp --write-auto-subs --skip-download`
6. `youtube-dl` subtitle fallback when available
7. direct YouTube timedtext endpoint variants
8. noembed/oEmbed metadata
9. Piped frontend subtitle discovery
10. local sidecar subtitles if local media was supplied
11. optional local ASR if `--local-media` and `--allow-local-asr` are supplied

## Download fallback

Only use this when transcript/caption resources fail.

Download the video into the workspace `tmp/videos/` folder:

```bash
mkdir -p tmp/videos
yt-dlp --no-playlist \
  --write-info-json \
  --restrict-filenames \
  -f "best[ext=mp4]/best" \
  -o "tmp/videos/%(title).180B-%(id)s.%(ext)s" \
  "$VIDEO_URL"
```

If a provisioned cookies file is needed:

```bash
yt-dlp --cookies "/secure/path/cookies.txt" \
  --no-playlist \
  --write-info-json \
  --restrict-filenames \
  -f "best[ext=mp4]/best" \
  -o "tmp/videos/%(title).180B-%(id)s.%(ext)s" \
  "$VIDEO_URL"
```

Do not print cookie file contents.

## Transcribe downloaded fallback video

After download, find the media file:

```bash
find tmp/videos -maxdepth 1 -type f \
  \( -name '*.mp4' -o -name '*.mkv' -o -name '*.webm' -o -name '*.mov' -o -name '*.m4a' -o -name '*.mp3' \) \
  -print
```

Then run ASR:

```bash
python3 scripts/local_asr_faster_whisper.py "tmp/videos/<downloaded-file>" \
  --out-dir "tmp/transcripts/VIDEO_ID-local-asr" \
  --model small \
  --device cpu \
  --compute-type int8
```

Label the transcript source as:

```text
local ASR/faster-whisper from downloaded video
```

Do not call it official captions.

## Optional combined report

For YouTube links, after download you can rerun the main helper so the report includes both URL metadata and ASR fallback:

```bash
python3 scripts/fetch_youtube_content.py "$VIDEO_URL" \
  --local-media "tmp/videos/<downloaded-file>" \
  --allow-local-asr \
  --asr-model small \
  --asr-device cpu \
  --asr-compute-type int8 \
  --out-dir "tmp/transcripts/VIDEO_ID-combined"
```

## Reporting checklist

When finished, report:

```text
Transcript source: <captionTracks | yt-dlp subtitles | timedtext | Piped | local ASR/faster-whisper | local ASR/faster-whisper from downloaded video | unavailable>
Transcript saved at: <path or unavailable>
Downloaded video: <path or not needed>
Report/metadata saved at: <path>
Methods tried: <short list>
```

If no transcript is found, state exactly what failed and avoid hallucinating the video content from the title alone.
