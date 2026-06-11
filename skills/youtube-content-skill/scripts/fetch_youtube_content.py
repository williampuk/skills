#!/usr/bin/env python3
"""
Fetch YouTube metadata and transcripts/captions using a repeatable retrieval ladder.

This script intentionally uses only Python stdlib plus optional external binaries
(curl/wget, yt-dlp, youtube-dl, ffprobe, ffmpeg, whisper) if present.

Output directory:
  /tmp/youtube_content_<video_id>_<timestamp>/

Key files:
  report.md
  metadata.json
  transcript.txt
  transcript_full.txt
  raw/*
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree

PIPED_INSTANCES = [
    "https://piped.video",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi-libre.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.syncpundit.io",
]

USER_AGENT = "Mozilla/5.0 (compatible; youtube-content-fetcher-skill/1.0)"


def run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 90) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or f"Timed out after {timeout}s"


def http_get(url: str, timeout: int = 30) -> Tuple[Optional[bytes], Optional[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), None
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        return None, f"{type(exc).__name__}: {exc}"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def extract_video_id(value: str) -> Optional[str]:
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    try:
        parsed = urllib.parse.urlparse(value)
        host = parsed.netloc.lower()
        path = parsed.path.strip("/")
        qs = urllib.parse.parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            vid = qs["v"][0]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                return vid
        if host.endswith("youtu.be") and path:
            vid = path.split("/")[0]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                return vid
        for prefix in ("shorts/", "embed/", "live/"):
            if path.startswith(prefix):
                vid = path[len(prefix):].split("/")[0]
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                    return vid
    except Exception:
        pass
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", value)
    return m.group(1) if m else None


def decode_js_json_string(s: str) -> str:
    # HTML can contain escaped JSON with \u0026 etc. Let json decoder help when possible.
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s.replace("\\u0026", "&").replace("\\/", "/")


def find_balanced_json_after(html_text: str, marker: str) -> Optional[Dict[str, Any]]:
    idx = html_text.find(marker)
    if idx < 0:
        return None
    brace = html_text.find("{", idx)
    if brace < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(brace, len(html_text)):
        ch = html_text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = html_text[brace : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        return None
    return None


def iter_caption_tracks(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        if "captionTracks" in obj and isinstance(obj["captionTracks"], list):
            for track in obj["captionTracks"]:
                if isinstance(track, dict):
                    yield track
        for v in obj.values():
            yield from iter_caption_tracks(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_caption_tracks(item)


def parse_watch_metadata(html_text: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    initial = find_balanced_json_after(html_text, "ytInitialPlayerResponse")
    if initial:
        metadata["ytInitialPlayerResponse_found"] = True
        vd = initial.get("videoDetails") or {}
        for key in ("title", "author", "shortDescription", "lengthSeconds", "videoId", "channelId"):
            if key in vd:
                metadata[key] = vd[key]
        micro = initial.get("microformat", {}).get("playerMicroformatRenderer", {})
        for src_key, dst_key in (
            ("publishDate", "publishDate"),
            ("uploadDate", "uploadDate"),
            ("category", "category"),
        ):
            if src_key in micro:
                metadata[dst_key] = micro[src_key]
        tracks = list(iter_caption_tracks(initial))
        if tracks:
            metadata["captionTracks"] = tracks
    else:
        metadata["ytInitialPlayerResponse_found"] = False
    title_m = re.search(r"<title>(.*?)</title>", html_text, flags=re.S | re.I)
    if title_m and "title" not in metadata:
        metadata["title"] = html.unescape(re.sub(r"\s+", " ", title_m.group(1))).replace(" - YouTube", "").strip()
    return metadata


def strip_vtt(text: str) -> str:
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip("\ufeff").strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT") or line.upper().startswith("NOTE"):
            continue
        if re.match(r"^\d+$", line):
            continue
        if "-->" in line:
            continue
        if line.startswith(("STYLE", "REGION", "Kind:", "Language:")):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = html.unescape(line).strip()
        if line:
            lines.append(line)
    return dedupe_caption_lines(lines)


def strip_srt(text: str) -> str:
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or re.match(r"^\d+$", line) or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = html.unescape(line).strip()
        if line:
            lines.append(line)
    return dedupe_caption_lines(lines)


def strip_xml_captions(text: str) -> str:
    try:
        root = ElementTree.fromstring(text)
        values: List[str] = []
        for elem in root.iter():
            tag = elem.tag.split("}")[-1].lower()
            if tag in {"text", "p", "span"} and elem.text:
                val = html.unescape(elem.text).strip()
                if val:
                    values.append(val)
        if values:
            return dedupe_caption_lines(values)
    except Exception:
        pass
    # Fallback for fragments or YouTube XML text nodes.
    values = []
    for m in re.finditer(r"<text[^>]*>(.*?)</text>", text, flags=re.S | re.I):
        val = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if val:
            values.append(val)
    return dedupe_caption_lines(values)


def dedupe_caption_lines(lines: List[str]) -> str:
    # YouTube auto VTT often repeats rolling windows. Keep it simple and conservative.
    cleaned: List[str] = []
    prev = None
    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line == prev:
            continue
        cleaned.append(line)
        prev = line
    # Join as paragraphs-ish while preserving readability.
    return "\n".join(cleaned).strip() + ("\n" if cleaned else "")


def captions_to_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    lower = path.name.lower()
    sample = text[:200].lstrip()
    if lower.endswith(".vtt") or sample.upper().startswith("WEBVTT"):
        return strip_vtt(text)
    if lower.endswith(".srt"):
        return strip_srt(text)
    if lower.endswith((".xml", ".ttml", ".srv1", ".srv2", ".srv3")) or sample.startswith("<"):
        return strip_xml_captions(text)
    return text


def choose_best_caption_file(files: List[Path]) -> Optional[Path]:
    if not files:
        return None
    def score(p: Path) -> Tuple[int, int]:
        n = p.name.lower()
        s = 0
        if ".en" in n or "english" in n:
            s += 50
        if "auto" not in n and "asr" not in n:
            s += 10
        if n.endswith(".vtt"):
            s += 5
        return (s, -len(n))
    return sorted(files, key=score, reverse=True)[0]


def save_transcript(out_dir: Path, text: str, source: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    write_text(out_dir / "transcript.txt", cleaned + "\n")
    write_text(out_dir / "transcript_full.txt", cleaned + "\n")
    write_text(out_dir / "transcript_source.txt", source + "\n")
    return True


def fetch_and_convert_caption_url(url: str, dest: Path) -> Optional[str]:
    data, err = http_get(url, timeout=45)
    if not data:
        write_text(dest.with_suffix(dest.suffix + ".error.txt"), err or "unknown error")
        return None
    write_bytes(dest, data)
    try:
        text = captions_to_text(dest)
        return text if text.strip() else None
    except Exception as exc:
        write_text(dest.with_suffix(dest.suffix + ".parse_error.txt"), repr(exc))
        return None


def best_track(tracks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not tracks:
        return None
    def lang_code(t: Dict[str, Any]) -> str:
        return str(t.get("languageCode") or t.get("code") or "").lower()
    def name(t: Dict[str, Any]) -> str:
        n = t.get("name")
        if isinstance(n, dict):
            return json.dumps(n, ensure_ascii=False).lower()
        return str(n or "").lower()
    def score(t: Dict[str, Any]) -> int:
        s = 0
        lc = lang_code(t)
        nm = name(t)
        if lc == "en":
            s += 100
        elif lc.startswith("en"):
            s += 80
        if "english" in nm:
            s += 20
        if not (t.get("kind") == "asr" or t.get("autoGenerated") is True or "auto" in nm):
            s += 10
        if t.get("baseUrl") or t.get("url"):
            s += 5
        return s
    return sorted(tracks, key=score, reverse=True)[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="YouTube URL or video ID")
    ap.add_argument("--local-media", help="Optional path to downloaded MP4/MKV/WebM", default=None)
    ap.add_argument("--out-dir", help="Override output directory", default=None)
    ap.add_argument("--allow-local-asr", action="store_true", help="If no captions are found, transcribe the local media file with faster-whisper when installed")
    ap.add_argument("--asr-model", default="small", help="faster-whisper model for --allow-local-asr, e.g. tiny/base/small/medium/large-v3")
    ap.add_argument("--asr-device", default="cpu", help="faster-whisper device for --allow-local-asr: cpu/cuda/auto")
    ap.add_argument("--asr-compute-type", default="int8", help="faster-whisper compute_type for --allow-local-asr")
    args = ap.parse_args()

    video_id = extract_video_id(args.input)
    if not video_id:
        print("Could not extract YouTube video ID", file=sys.stderr)
        return 2

    url = f"https://www.youtube.com/watch?v={video_id}"
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir or f"/tmp/youtube_content_{video_id}_{ts}")
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    report: List[str] = [f"# YouTube content fetch report", "", f"Video ID: `{video_id}`", f"URL: {url}", ""]
    metadata: Dict[str, Any] = {"videoId": video_id, "url": url, "input": args.input}

    # 1. Direct page fetch using Python and curl/wget if available.
    data, err = http_get(url, timeout=30)
    if data:
        write_bytes(raw / "youtube_watch.html", data)
        html_text = data.decode("utf-8", errors="replace")
        md = parse_watch_metadata(html_text)
        metadata.update({k: v for k, v in md.items() if k != "captionTracks"})
        if "captionTracks" in md:
            metadata["captionTracks_count"] = len(md["captionTracks"])
            write_text(raw / "caption_tracks_from_watch.json", json.dumps(md["captionTracks"], ensure_ascii=False, indent=2))
        report.append("- Direct YouTube watch page fetch: success")
    else:
        report.append(f"- Direct YouTube watch page fetch: failed: {err}")

    for bin_name in ("curl", "wget"):
        if shutil.which(bin_name):
            cmd = [bin_name]
            if bin_name == "curl":
                cmd += ["-L", "--compressed", "-A", USER_AGENT, url]
            else:
                cmd += ["-O", "-", url]
            code, stdout, stderr = run(cmd, timeout=45)
            write_text(raw / f"{bin_name}_watch.stdout", stdout)
            write_text(raw / f"{bin_name}_watch.stderr", stderr)
            report.append(f"- {bin_name} watch page attempt: exit {code}")

    # 2. Fetch captionTrack if found.
    tracks_path = raw / "caption_tracks_from_watch.json"
    if tracks_path.exists():
        try:
            tracks = json.loads(tracks_path.read_text(encoding="utf-8"))
            track = best_track(tracks)
            if track:
                cap_url = track.get("baseUrl") or track.get("url")
                if cap_url:
                    cap_url = decode_js_json_string(str(cap_url))
                    if "fmt=" not in cap_url:
                        cap_url += ("&" if "?" in cap_url else "?") + "fmt=vtt"
                    text = fetch_and_convert_caption_url(cap_url, raw / "captiontracks_best.vtt")
                    if text and save_transcript(out_dir, text, "captionTracks from YouTube watch page"):
                        report.append("- captionTracks extraction: success; transcript saved")
                    else:
                        report.append("- captionTracks extraction: URL found but transcript parse/fetch failed")
        except Exception as exc:
            report.append(f"- captionTracks extraction: failed: {exc!r}")

    # 3. yt-dlp attempts.
    for label, cmd in [
        ("yt-dlp auto subtitles", ["yt-dlp", "--write-auto-subs", "--skip-download", url, "-o", str(raw / "yt_video")]),
        ("yt-dlp manual English subtitles", ["yt-dlp", "--write-subs", "--skip-download", "--sub-lang", "en", url, "-o", str(raw / "yt_video")]),
    ]:
        code, stdout, stderr = run(cmd, timeout=180)
        write_text(raw / (label.replace(" ", "_") + ".stdout"), stdout)
        write_text(raw / (label.replace(" ", "_") + ".stderr"), stderr)
        report.append(f"- {label}: exit {code}")
        caption_files = list(raw.glob("yt_video*.*"))
        caption_files = [p for p in caption_files if p.suffix.lower() in {".vtt", ".srt", ".ttml", ".xml", ".srv1", ".srv2", ".srv3"}]
        best = choose_best_caption_file(caption_files)
        if best and not (out_dir / "transcript.txt").exists():
            text = captions_to_text(best)
            if save_transcript(out_dir, text, label):
                report.append(f"  - transcript saved from `{best.name}`")

    # 4. youtube-dl fallback.
    code, stdout, stderr = run(["youtube-dl", "--write-auto-sub", "--skip-download", url, "-o", str(raw / "youtube_dl_video")], timeout=180)
    write_text(raw / "youtube_dl_auto.stdout", stdout)
    write_text(raw / "youtube_dl_auto.stderr", stderr)
    report.append(f"- youtube-dl auto subtitles: exit {code}")
    if not (out_dir / "transcript.txt").exists():
        caption_files = [p for p in raw.glob("youtube_dl_video*.*") if p.suffix.lower() in {".vtt", ".srt", ".ttml", ".xml", ".srv1", ".srv2", ".srv3"}]
        best = choose_best_caption_file(caption_files)
        if best:
            text = captions_to_text(best)
            if save_transcript(out_dir, text, "youtube-dl auto subtitles"):
                report.append(f"  - transcript saved from `{best.name}`")

    # 5. Direct timedtext endpoint variants.
    timedtext_urls = [
        f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en",
        f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&fmt=vtt",
        f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&kind=asr&fmt=vtt",
        f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&kind=asr",
    ]
    for i, turl in enumerate(timedtext_urls, start=1):
        ext = ".vtt" if "fmt=vtt" in turl else ".xml"
        text = fetch_and_convert_caption_url(turl, raw / f"timedtext_{i}{ext}")
        if text and len(text.strip()) > 20:
            report.append(f"- direct timedtext variant {i}: success")
            if not (out_dir / "transcript.txt").exists():
                save_transcript(out_dir, text, f"direct YouTube timedtext variant {i}")
        else:
            report.append(f"- direct timedtext variant {i}: no usable transcript")

    # 6. Metadata APIs.
    for name, murl in [
        ("noembed", f"https://noembed.com/embed?url={urllib.parse.quote(url, safe='')}") ,
        ("youtube_oembed", f"https://www.youtube.com/oembed?url={urllib.parse.quote(url, safe='')}&format=json"),
    ]:
        data, err = http_get(murl, timeout=30)
        if data:
            write_bytes(raw / f"{name}.json", data)
            try:
                metadata[name] = json.loads(data.decode("utf-8", errors="replace"))
            except Exception:
                metadata[name] = {"raw_file": str(raw / f"{name}.json")}
            report.append(f"- {name} metadata: success")
        else:
            report.append(f"- {name} metadata: failed: {err}")

    # 7. Piped frontend caption discovery.
    for instance in PIPED_INSTANCES:
        streams_url = f"{instance.rstrip('/')}/api/v1/streams/{video_id}"
        data, err = http_get(streams_url, timeout=30)
        safe_name = re.sub(r"[^A-Za-z0-9]+", "_", instance).strip("_")
        if not data:
            write_text(raw / f"piped_{safe_name}.error.txt", err or "unknown error")
            report.append(f"- Piped {instance}: failed")
            continue
        write_bytes(raw / f"piped_{safe_name}.json", data)
        try:
            obj = json.loads(data.decode("utf-8", errors="replace"))
            if "title" in obj and "title" not in metadata:
                metadata["title"] = obj.get("title")
            subtitles = obj.get("subtitles") or []
            report.append(f"- Piped {instance}: success, subtitles={len(subtitles)}")
            if subtitles and not (out_dir / "transcript.txt").exists():
                track = best_track(subtitles)
                cap_url = track.get("url") if track else None
                if cap_url:
                    text = fetch_and_convert_caption_url(str(cap_url), raw / f"piped_{safe_name}_best_caption")
                    if text and save_transcript(out_dir, text, f"Piped subtitles via {instance}"):
                        report.append(f"  - transcript saved from Piped `{instance}`")
                        break
        except Exception as exc:
            report.append(f"- Piped {instance}: parse failed: {exc!r}")

    # 8. Local media fallback.
    if args.local_media:
        media = Path(args.local_media).expanduser()
        metadata["local_media"] = str(media)
        if media.exists():
            report.append(f"- Local media exists: {media}")
            # Sidecar subtitles near the media.
            sidecars: List[Path] = []
            for ext in (".vtt", ".srt", ".ttml", ".xml", ".srv1", ".srv2", ".srv3", ".json"):
                sidecars.extend(media.parent.glob(media.stem + "*" + ext))
            sidecars = sorted(set(sidecars))
            write_text(raw / "local_sidecars.txt", "\n".join(str(p) for p in sidecars))
            report.append(f"  - Local sidecar subtitle candidates: {len(sidecars)}")
            best = choose_best_caption_file([p for p in sidecars if p.suffix.lower() != ".json"])
            if best and not (out_dir / "transcript.txt").exists():
                text = captions_to_text(best)
                if save_transcript(out_dir, text, f"local sidecar subtitle {best}"):
                    report.append(f"  - transcript saved from local sidecar `{best}`")
            if shutil.which("ffprobe"):
                code, stdout, stderr = run(["ffprobe", "-hide_banner", "-i", str(media)], timeout=60)
                write_text(raw / "ffprobe.stdout", stdout)
                write_text(raw / "ffprobe.stderr", stderr)
                report.append(f"  - ffprobe: exit {code}")
            else:
                report.append("  - ffprobe: not installed")

            # Optional local ASR fallback. This is deliberately opt-in because it can be slow,
            # CPU/GPU intensive, and may require downloading a model the first time.
            if args.allow_local_asr and not (out_dir / "transcript.txt").exists():
                asr_script = Path(__file__).parent / "local_asr_faster_whisper.py"
                if asr_script.exists():
                    asr_dir = out_dir / "local_asr"
                    cmd = [
                        sys.executable,
                        str(asr_script),
                        str(media),
                        "--out-dir",
                        str(asr_dir),
                        "--model",
                        args.asr_model,
                        "--device",
                        args.asr_device,
                        "--compute-type",
                        args.asr_compute_type,
                    ]
                    code, stdout, stderr = run(cmd, timeout=7200)
                    write_text(raw / "local_asr.stdout", stdout)
                    write_text(raw / "local_asr.stderr", stderr)
                    report.append(f"  - local ASR faster-whisper: exit {code}")
                    asr_transcript = asr_dir / "local_asr_transcript.txt"
                    if code == 0 and asr_transcript.exists():
                        text = asr_transcript.read_text(encoding="utf-8", errors="replace")
                        if save_transcript(out_dir, text, f"local ASR faster-whisper model={args.asr_model}"):
                            report.append(f"  - transcript saved from local ASR `{asr_transcript}`")
                else:
                    report.append("  - local ASR requested but local_asr_faster_whisper.py is missing")
            elif not args.allow_local_asr and not (out_dir / "transcript.txt").exists():
                report.append("  - local ASR faster-whisper: skipped; pass --allow-local-asr to enable")
        else:
            report.append(f"- Local media path does not exist: {media}")

    transcript_exists = (out_dir / "transcript.txt").exists()
    metadata["transcript_found"] = transcript_exists
    if transcript_exists:
        metadata["transcript_path"] = str(out_dir / "transcript.txt")
        metadata["transcript_full_path"] = str(out_dir / "transcript_full.txt")
        try:
            metadata["transcript_chars"] = len((out_dir / "transcript.txt").read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    write_text(out_dir / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    report.append("")
    report.append(f"Transcript found: {'yes' if transcript_exists else 'no'}")
    report.append(f"Output directory: `{out_dir}`")
    write_text(out_dir / "report.md", "\n".join(report) + "\n")

    print(f"Output directory: {out_dir}")
    print(f"Report: {out_dir / 'report.md'}")
    if transcript_exists:
        print(f"Transcript: {out_dir / 'transcript.txt'}")
    else:
        print("Transcript: unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
