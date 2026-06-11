---
name: youtube-content-fetcher
description: Use this skill whenever the user gives a YouTube URL, YouTube video ID, local downloaded YouTube MP4 path, or asks to summarize/analyze/extract the content, transcript, subtitles, captions, chapters, slides, examples, quotes, or metadata from a YouTube video. This skill gives Claude a repeatable workflow for trying direct YouTube fetches, yt-dlp/youtube-dl subtitles, captionTracks/timedtext extraction, noembed/oEmbed metadata, Piped frontend caption discovery, sidecar subtitle files, local media inspection, and optional local ASR via faster-whisper, then saving transcripts and producing grounded summaries.
---

# YouTube Content Fetcher

This skill helps Claude reliably retrieve and analyze the content of a YouTube video when the user provides a YouTube link, video ID, or local media file path.

Use this skill when the user asks for any of the following:

- summarize a YouTube video
- get a YouTube transcript, subtitles, captions, ASR captions, or timedtext
- analyze a downloaded YouTube MP4 together with the source URL
- extract chapters, timestamps, key topics, slide content, code examples, quotes, or diagrams mentioned in a video
- compare multiple transcript acquisition methods
- save the raw transcript to a file for later analysis

## Core principle

Do not improvise a new one-off approach every time. Follow the ordered retrieval ladder below, record what worked and what failed, save artifacts under `/tmp`, then summarize from the best available transcript or captions.

Respect access controls and copyright. Do not bypass paywalls, private video restrictions, account-only access, DRM, or age-gated/login-only content. Prefer summaries and user-directed analysis. Only provide long verbatim transcript text when the user owns the video, has supplied the transcript/media themselves, or the transcript is clearly permitted for reuse.

## First action

If code execution and shell access are available, run the helper script:

```bash
python3 scripts/fetch_youtube_content.py "<youtube-url-or-video-id>" --local-media "<optional-local-mp4-path>"
```

The script creates a run directory like:

```text
/tmp/youtube_content_<video_id>_<timestamp>/
```

Important output files:

```text
report.md                    # What methods were tried and what worked
metadata.json                # Best metadata found
transcript.txt               # Clean transcript, if any
transcript_full.txt          # Same as transcript.txt, preserved for user inspection
raw/                         # Raw pages, captions, JSON, and command output
```

After running the script, read `report.md`, `metadata.json`, and `transcript.txt` if present. Base the answer on those files.

If the helper script is unavailable, follow the manual ladder in `references/manual_workflow.md`.

## Retrieval ladder

Use this order. Stop only after a good transcript is found, but still record enough diagnostics to explain the source.

1. **Normalize input**
   - Extract the YouTube video ID from `youtube.com/watch?v=...`, `youtu.be/...`, `/shorts/...`, `/embed/...`, or raw 11-character IDs.
   - Preserve the original URL and any local media path.

2. **Direct YouTube page fetch**
   - Try `curl -L` or `wget` against the watch URL.
   - Save the HTML under `raw/youtube_watch.html`.
   - Search the page for `captionTracks`, `playerCaptionsTracklistRenderer`, `ytInitialPlayerResponse`, `title`, `shortDescription`, `chapters`, and `lengthSeconds`.

3. **yt-dlp subtitle attempts**
   - Try auto-generated subtitles:
     ```bash
     yt-dlp --write-auto-subs --skip-download "<url>" -o /tmp/yt_video
     ```
   - Try human subtitles:
     ```bash
     yt-dlp --write-subs --skip-download --sub-lang en "<url>" -o /tmp/yt_video
     ```
   - Prefer English tracks, but keep other available language metadata if English is missing.

4. **youtube-dl fallback**
   - Try:
     ```bash
     youtube-dl --write-auto-sub --skip-download "<url>" -o /tmp/yt_video
     ```

5. **Extract captionTracks / timedtext URLs**
   - If the watch page contains caption track JSON, parse it.
   - Fetch `baseUrl` values directly.
   - Convert XML/VTT/TTML/SRV captions to plain text.

6. **Direct timedtext endpoint**
   - Try:
     ```text
     https://www.youtube.com/api/timedtext?v=<video_id>&lang=en
     ```
   - Also try `fmt=vtt`, `fmt=ttml`, and `kind=asr` variants.

7. **noembed / oEmbed metadata**
   - Fetch metadata from:
     ```text
     https://noembed.com/embed?url=https://www.youtube.com/watch?v=<video_id>
     https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=<video_id>&format=json
     ```
   - These usually provide metadata, not transcripts.

8. **Piped frontend caption discovery**
   - Query Piped `/streams/<video_id>` endpoints.
   - Look for a `subtitles` array.
   - Prefer manually uploaded English captions over auto-generated ASR captions, unless the user explicitly wants ASR.
   - Fetch subtitle URLs and convert to plain text.
   - Explain that “Piped worked” means a Piped frontend exposed caption URLs or proxied YouTube timedtext captions.

9. **Local media fallback**
   - Check for sidecar subtitle files near the MP4: `.vtt`, `.srt`, `.ttml`, `.srv1`, `.srv2`, `.srv3`, `.json`, `.info.json`.
   - Use `ffprobe` if available to inspect embedded subtitle streams and metadata.
   - If no transcript exists and the user owns/has rights to the media, use local ASR as an explicit fallback, not as the first choice.

10. **Optional local ASR with faster-whisper**
   - Use this when caption retrieval fails, captions are missing/low-quality, or the user only supplied a local audio/video file.
   - Prefer this helper when available:
     ```bash
     python3 scripts/local_asr_faster_whisper.py "<local-media-file>" --model small --device cpu --compute-type int8 --extract-wav
     ```
   - Or run the main helper with ASR enabled:
     ```bash
     python3 scripts/fetch_youtube_content.py "<youtube-url-or-video-id>" --local-media "<local-mp4-path>" --allow-local-asr --asr-model small
     ```
   - Do not install `faster-whisper`, download large model weights, or start long background jobs unless the user has asked for local ASR or has clearly authorized that approach.
   - Run ASR synchronously when the user expects the answer in the current session. Avoid `nohup ... &` unless the user explicitly asks for a background job and understands they must check the files/logs later.
   - Save timestamped text, JSON segments, and SRT output. Label the source as `local ASR`, not `YouTube captions`.

## Summarization requirements

When a transcript is available and the user asks for details, provide a comprehensive structured summary covering, when present:

- title, channel/uploader, duration, upload date, description, and source of transcript
- chapters/sections in order, with timestamps if available
- all major topics from beginning to end
- key technical concepts and definitions
- strategies, algorithms, patterns, and tradeoffs
- numerical examples, scenarios, diagrams, slides, code examples, screenshots, or whiteboard content mentioned
- failure modes, caveats, edge cases, and operational challenges
- memorable short quotes, staying within copyright-safe quote limits
- transcript file path, if saved

For system design videos about caching, explicitly look for:

- cache-aside / lazy loading
- read-through
- write-through
- write-behind / write-back
- refresh-ahead
- eviction: LRU, LFU, FIFO, TTL, random, size-based
- cache stampede / thundering herd
- invalidation strategies
- consistency, stale reads, negative caching, hot keys
- distributed caching, consistent hashing, replication, sharding, failover
- Redis/Memcached/CDN/browser-cache/database-cache mentions

## Reporting format

When finished, include:

```text
Transcript source: <yt-dlp manual subtitles | yt-dlp auto ASR | captionTracks | timedtext | Piped | local sidecar | local ASR/faster-whisper | unavailable>
Transcript saved at: <path or unavailable>
Metadata saved at: <path or unavailable>
Methods tried: <short list of successes/failures>
```

Then provide the user-facing summary.

## Failure handling

If no transcript is found:

- Say clearly that transcript retrieval failed.
- Explain which methods were tried.
- Use available metadata, description, chapters, thumbnails, or local media metadata only if available.
- Suggest the user provide a `.vtt`, `.srt`, `.json`, or downloaded subtitle file, or permit local ASR on the media file using faster-whisper/Whisper.

Do not hallucinate video content from only the title.
