#!/usr/bin/env python3
"""
Transcribe a local media/audio file using faster-whisper when installed.

This script is intentionally optional. It does not download YouTube content.
It only works on a local file that the user supplied or has permission to analyze.

Outputs:
  <out-dir>/local_asr_transcript.txt
  <out-dir>/local_asr_transcript_full.txt
  <out-dir>/local_asr_transcript.json
  <out-dir>/local_asr_report.md
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple


def run(cmd: List[str], timeout: int = 3600) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or f"Timed out after {timeout}s"


def sec_to_srt_time(value: float) -> str:
    ms_total = int(round(value * 1000))
    ms = ms_total % 1000
    total_seconds = ms_total // 1000
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("media", help="Local audio/video file to transcribe")
    ap.add_argument("--out-dir", default=None, help="Output directory; default: /tmp/local_asr_<timestamp>")
    ap.add_argument("--model", default="small", help="faster-whisper model name or local model path, e.g. tiny/base/small/medium/large-v3")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda", "auto"], help="Device for faster-whisper")
    ap.add_argument("--compute-type", default="int8", help="compute_type, e.g. int8 for CPU, float16 or int8_float16 for CUDA")
    ap.add_argument("--language", default="en", help="Language hint; use empty string to auto-detect")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--vad-filter", action="store_true", default=True, help="Enable VAD filtering; default on")
    ap.add_argument("--no-vad-filter", dest="vad_filter", action="store_false")
    ap.add_argument("--extract-wav", action="store_true", help="Use ffmpeg to extract 16 kHz mono WAV before ASR")
    args = ap.parse_args()

    media = Path(args.media).expanduser()
    if not media.exists():
        print(f"Media file does not exist: {media}", file=sys.stderr)
        return 2

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir or f"/tmp/local_asr_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    report: List[str] = ["# Local ASR faster-whisper report", "", f"Input: `{media}`", f"Output directory: `{out_dir}`", ""]

    asr_input = media
    if args.extract_wav:
        if not shutil.which("ffmpeg"):
            report.append("- ffmpeg extraction requested, but ffmpeg is not installed")
            (out_dir / "local_asr_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
            return 3
        wav = out_dir / "audio_16k_mono.wav"
        code, stdout, stderr = run(["ffmpeg", "-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(wav)], timeout=1800)
        (out_dir / "ffmpeg.stdout").write_text(stdout, encoding="utf-8", errors="replace")
        (out_dir / "ffmpeg.stderr").write_text(stderr, encoding="utf-8", errors="replace")
        report.append(f"- ffmpeg audio extraction: exit {code}")
        if code != 0 or not wav.exists():
            (out_dir / "local_asr_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
            return 4
        asr_input = wav

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as exc:
        report.append(f"- faster-whisper import failed: {type(exc).__name__}: {exc}")
        report.append("- Install only with user permission, for example: `python3 -m pip install faster-whisper`.")
        (out_dir / "local_asr_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        return 5

    print(f"Loading faster-whisper model {args.model!r} on {args.device} compute_type={args.compute_type}...", flush=True)
    t0 = time.time()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    report.append(f"- Model loaded in {time.time() - t0:.1f}s: {args.model}, device={args.device}, compute_type={args.compute_type}")

    kwargs = {
        "beam_size": args.beam_size,
        "vad_filter": args.vad_filter,
    }
    if args.language:
        kwargs["language"] = args.language

    print(f"Transcribing {asr_input}...", flush=True)
    t1 = time.time()
    segments_iter, info = model.transcribe(str(asr_input), **kwargs)

    segments = []
    txt_lines: List[str] = []
    srt_lines: List[str] = []
    for i, seg in enumerate(segments_iter, start=1):
        text = seg.text.strip()
        item = {"id": i, "start": seg.start, "end": seg.end, "text": text}
        segments.append(item)
        txt_lines.append(f"[{seg.start:9.2f} -> {seg.end:9.2f}] {text}")
        srt_lines.extend([str(i), f"{sec_to_srt_time(seg.start)} --> {sec_to_srt_time(seg.end)}", text, ""])
        print(f"[{seg.start:9.2f}] {text}", flush=True)

    elapsed = time.time() - t1
    payload = {
        "input": str(media),
        "asr_input": str(asr_input),
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "elapsed_seconds": elapsed,
        "segments": segments,
    }

    text = "\n".join(txt_lines).strip() + "\n"
    (out_dir / "local_asr_transcript.txt").write_text(text, encoding="utf-8")
    (out_dir / "local_asr_transcript_full.txt").write_text(text, encoding="utf-8")
    (out_dir / "local_asr_transcript.srt").write_text("\n".join(srt_lines).strip() + "\n", encoding="utf-8")
    (out_dir / "local_asr_transcript.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report.append(f"- Transcription completed in {elapsed:.1f}s")
    report.append(f"- Detected language: {payload['language']} prob={payload['language_probability']}")
    report.append(f"- Duration: {payload['duration']}")
    report.append(f"- Segments: {len(segments)}")
    report.append(f"- Transcript: `{out_dir / 'local_asr_transcript.txt'}`")
    (out_dir / "local_asr_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"Transcript: {out_dir / 'local_asr_transcript.txt'}")
    print(f"JSON: {out_dir / 'local_asr_transcript.json'}")
    print(f"Report: {out_dir / 'local_asr_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
