# Skills

This repository contains Claude Skills.

## Video Transcriber

The main media skill is in:

```text
skills/youtube-content-skill/
```

The skill name in `SKILL.md` is `video-transcriber`.

It handles two cases:

1. Local video/audio file: transcribe directly with Python + `faster-whisper`.
2. Web video link: try web transcript/caption resources first; if those fail, download the video to `tmp/videos/` with `yt-dlp`, then transcribe the downloaded file.

Install dependencies from the skill folder:

```bash
cd skills/youtube-content-skill
python3 -m pip install -r requirements.txt
```

Cookie file guidance for authenticated `yt-dlp` access is documented in:

```text
skills/youtube-content-skill/references/COOKIES.md
```
