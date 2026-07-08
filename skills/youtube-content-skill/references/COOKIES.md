# Cookie File Format for yt-dlp

This skill expects cookies to be provisioned as a file, not extracted from the browser at runtime.

Pass the file to `yt-dlp` with:

```bash
yt-dlp --cookies /secure/path/cookies.txt "<url>"
```

or set:

```bash
export YTDLP_COOKIES_FILE=/secure/path/cookies.txt
yt-dlp --cookies "$YTDLP_COOKIES_FILE" "<url>"
```

## Required format

The file must be in Mozilla/Netscape `cookies.txt` format. The first line should be one of:

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

Use cookies only when the user has provided/provisioned them and is authorized to access the content. Do not use cookies to bypass paywalls, private video restrictions, DRM, or access controls.
