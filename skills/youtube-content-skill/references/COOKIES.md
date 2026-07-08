# Cookie File Format for yt-dlp

This skill expects cookies to be provisioned as a file path in the `YTDLP_COOKIES_FILE` environment variable.

The agent should not ask the user to pass a cookie path directly in each `yt-dlp` command. The convention is:

```bash
export YTDLP_COOKIES_FILE=/secure/path/cookies.txt
```

When downloading fallback media, the agent should check whether the variable is set:

```bash
if [ -n "${YTDLP_COOKIES_FILE:-}" ]; then
  YTDLP_COOKIE_ARGS=(--cookies "$YTDLP_COOKIES_FILE")
else
  YTDLP_COOKIE_ARGS=()
fi
```

Then pass the argument array to `yt-dlp`:

```bash
yt-dlp "${YTDLP_COOKIE_ARGS[@]}" "<url>"
```

Behavior:

- If `YTDLP_COOKIES_FILE` is set, use `--cookies "$YTDLP_COOKIES_FILE"`.
- If `YTDLP_COOKIES_FILE` is not set, do not add any cookie option.
- Never print the cookie file contents.

## Required cookie file format

The file referenced by `YTDLP_COOKIES_FILE` must be in Mozilla/Netscape `cookies.txt` format. The first line should be one of:

```text
# Netscape HTTP Cookie File
```

or:

```text
# HTTP Cookie File
```

Each cookie row is tab-separated:

```text
<domain> <include-subdomains> <path> <secure> <expiry> <name> <value>
```

Example shape with fake values:

```text
# Netscape HTTP Cookie File
.youtube.com	TRUE	/	TRUE	1893456000	LOGIN_INFO	fake-value
.youtube.com	TRUE	/	TRUE	1893456000	SAPISID	fake-value
```

Use real tab characters between columns. Do not replace tabs with spaces.

## Security handling

- Treat the cookies file like a password or session token.
- Do not commit it to git.
- Do not paste its contents into chat.
- Store it outside the repo, for example under a private secrets directory.
- Delete it when no longer needed.
- Never print cookie values in logs or responses.

## When to use cookies

Use cookies only when the user has provisioned `YTDLP_COOKIES_FILE` and is authorized to access the content. Do not use cookies to bypass paywalls, private video restrictions, DRM, or access controls.
