# Video Transcriber Skill

Install this folder as a Claude Skill. The important file is `SKILL.md`; the scripts in `scripts/` give Claude a deterministic workflow for local media transcription and web-video transcript retrieval.

## What this skill does

This is one versatile skill:

- local video/audio file -> transcribe directly with Python + `faster-whisper`
- web video URL -> try web transcript/caption resources first
- if web transcript resources fail -> download the video to `tmp/videos/` with `yt-dlp`, then transcribe that local file

## Example: local file

```text
Use the Video Transcriber skill to transcribe ./meeting.mp4 and save the transcript under tmp/transcripts.
```

The skill should run:

```bash
python3 scripts/local_asr_faster_whisper.py ./meeting.mp4 \
  --out-dir tmp/transcripts/meeting \
  --model small \
  --device cpu \
  --compute-type int8
```

## Example: YouTube/web link

```text
Use the Video Transcriber skill to analyze this video: https://www.youtube.com/watch?v=1NngTUYPdpI
Save the transcript under tmp/transcripts and summarize all sections.
```

The skill should first run the transcript retrieval ladder:

```bash
python3 scripts/fetch_youtube_content.py "https://www.youtube.com/watch?v=1NngTUYPdpI" \
  --out-dir tmp/transcripts/1NngTUYPdpI
```

If no transcript is found, it should download the video only then. The agent should check `YTDLP_COOKIES_FILE`; if it is set, use it, and if not, omit the cookie option:

```bash
mkdir -p tmp/videos
if [ -n "${YTDLP_COOKIES_FILE:-}" ]; then
  YTDLP_COOKIE_ARGS=(--cookies "$YTDLP_COOKIES_FILE")
else
  YTDLP_COOKIE_ARGS=()
fi

yt-dlp "${YTDLP_COOKIE_ARGS[@]}" \
  --no-playlist --write-info-json --restrict-filenames \
  -f "best[ext=mp4]/best" \
  -o "tmp/videos/%(title).180B-%(id)s.%(ext)s" \
  "https://www.youtube.com/watch?v=1NngTUYPdpI"
```

Then transcribe the downloaded file with `local_asr_faster_whisper.py`.

## Dependencies

Recommended:

```bash
python3 -m pip install -r requirements.txt
```

Equivalent direct install:

```bash
python3 -m pip install yt-dlp faster-whisper
```

Install `ffmpeg` if you want optional audio extraction or more robust media handling.

## Cookies

If a site requires authenticated access, provision a Netscape/Mozilla `cookies.txt` file path through the `YTDLP_COOKIES_FILE` environment variable:

```bash
export YTDLP_COOKIES_FILE=/secure/path/cookies.txt
```

The agent should check whether this variable is set. If set, it should pass `--cookies "$YTDLP_COOKIES_FILE"` to `yt-dlp`; if not set, it should not add any cookie option. See `references/COOKIES.md`.
