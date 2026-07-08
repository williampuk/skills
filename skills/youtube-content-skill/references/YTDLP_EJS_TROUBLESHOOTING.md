# yt-dlp YouTube EJS / n-challenge Troubleshooting

Use this guide when `yt-dlp` can fetch a YouTube page but cannot list/download normal audio/video formats, especially when logs include messages like:

```text
n challenge solving failed
Ensure you have a supported JavaScript runtime and challenge solver script distribution installed
Only images are available for download
```

This usually means YouTube format extraction needs yt-dlp's External JavaScript Scripts (EJS) support, but the environment is missing either:

1. a supported JavaScript runtime, or
2. the `yt-dlp-ejs` challenge solver scripts.

## First: collect diagnostics

Run these before changing commands:

```bash
yt-dlp --version
python3 -m pip show yt-dlp yt-dlp-ejs 2>/dev/null || true
command -v deno || true
command -v node || true
command -v qjs || true
yt-dlp --verbose --list-formats "<youtube-url>" 2>&1 | tee tmp/yt-dlp-verbose.log
```

Look in the verbose output for available JS runtimes and EJS warnings.

## Preferred fix for pip-based environments

If `yt-dlp` was installed with pip/pipx, upgrade using the default dependency group:

```bash
python3 -m pip install -U "yt-dlp[default]"
```

This installs/updates the `yt-dlp-ejs` companion package used for YouTube challenge solving.

Then install a supported JS runtime. Prefer Deno when available because yt-dlp enables it by default:

```bash
# Use the OS/package-manager method appropriate for the machine.
# Examples only:
brew install deno
# or
sudo apt-get update && sudo apt-get install -y deno
```

If Deno is available in `PATH`, no extra `--js-runtimes` option is normally needed.

## Node fallback

If Deno is not installed but Node is installed, first check the version:

```bash
node --version
```

yt-dlp's EJS docs require a modern Node runtime. If Node is available and supported, enable it explicitly:

```bash
yt-dlp --js-runtimes node --list-formats "<youtube-url>"
```

For download fallback commands, add `--js-runtimes node` before the URL.

## QuickJS fallback

If QuickJS is installed as `qjs`, enable it explicitly:

```bash
yt-dlp --js-runtimes quickjs --list-formats "<youtube-url>"
```

QuickJS can be slower than Deno/Node in some environments.

## Runtime argument helper

Before a download/list-formats command, build runtime arguments like this:

```bash
YTDLP_JS_ARGS=()
if command -v deno >/dev/null 2>&1; then
  # Deno is enabled by default by yt-dlp. No explicit arg needed.
  :
elif command -v node >/dev/null 2>&1; then
  YTDLP_JS_ARGS=(--js-runtimes node)
elif command -v qjs >/dev/null 2>&1; then
  YTDLP_JS_ARGS=(--js-runtimes quickjs)
else
  echo "No supported JS runtime found. Install Deno first, or Node/QuickJS as fallback." >&2
fi
```

Keep cookie handling separate:

```bash
YTDLP_COOKIE_ARGS=()
if [ -n "${YTDLP_COOKIES_FILE:-}" ]; then
  YTDLP_COOKIE_ARGS=(--cookies "$YTDLP_COOKIES_FILE")
fi
```

Then run:

```bash
yt-dlp "${YTDLP_JS_ARGS[@]}" "${YTDLP_COOKIE_ARGS[@]}" \
  --no-playlist \
  --list-formats \
  "<youtube-url>"
```

## If EJS scripts are still missing

If a JS runtime exists but the log still says EJS/challenge solver scripts are missing, update/install yt-dlp with the default dependency group again:

```bash
python3 -m pip install -U "yt-dlp[default]"
```

If the environment cannot install Python packages but has Deno, a last-resort command may allow remote EJS components:

```bash
yt-dlp --remote-components ejs:npm --list-formats "<youtube-url>"
```

Use remote components only when the user is comfortable allowing yt-dlp to fetch those helper components at runtime.

## Do not stop at storyboard-only formats

If `--list-formats` shows only `sb0`, `sb1`, `sb2`, `sb3`, or `mhtml` storyboards, that is not a usable video download. Treat it as extraction failure and apply the EJS/JS-runtime steps above before falling back or reporting failure.
