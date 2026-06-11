# YouTube Content Fetcher Skill

Install this folder as a Claude Skill. The important file is `SKILL.md`; the script in `scripts/` gives Claude a deterministic retrieval ladder.

Example use after installing:

```text
Use the YouTube Content Fetcher skill to analyze this video: https://www.youtube.com/watch?v=1NngTUYPdpI
Save the transcript under /tmp and summarize all sections.
```


Optional local ASR dependency:

```bash
python3 -m pip install faster-whisper
```

For local ASR, install `ffmpeg` too if you want the helper to extract a normalized WAV from MP4/MKV/WebM.
