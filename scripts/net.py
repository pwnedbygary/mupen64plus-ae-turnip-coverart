"""Polite, sequential HTTP for the cover-art build.

One request at a time, at least PAUSE seconds apart, a User-Agent naming this work, one retry
per file (network error or 5xx), and a hard stop at the first HTTP 429 or at a run of three
failed responses (5xx or network error). Only the hosts the brief allows are reachable.
"""
import subprocess
import time
import urllib.error
import urllib.request

UA = "mupen64plus-ae-turnip-coverart-builder/1 (one-time build of a cover-art set; sequential, paced)"
PAUSE = 0.5

ALLOWED = (
    "https://github.com/libretro/libretro-database",
    "https://github.com/libretro/libretro-thumbnails",
    "https://github.com/libretro-thumbnails/",
    "https://raw.githubusercontent.com/libretro/libretro-database/",
    "https://raw.githubusercontent.com/libretro/libretro-thumbnails/",
    "https://raw.githubusercontent.com/libretro-thumbnails/",
    "https://api.github.com/repos/libretro/libretro-database/",
    "https://api.github.com/repos/libretro-thumbnails/",
    "https://thumbnails.libretro.com/",
)


class Stop(Exception):
    pass


_last = [time.monotonic()]
_fail_run = [0]


def check_url(url):
    if not url.startswith(ALLOWED) or "zurita" in url.lower():
        raise Stop("URL outside the allowed hosts: " + url)


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_Redirects())


def _pace():
    wait = _last[0] + PAUSE - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


def _count(failed, what):
    if failed:
        _fail_run[0] += 1
        if _fail_run[0] >= 3:
            raise Stop("three failed responses in a row, last: " + what)
    else:
        _fail_run[0] = 0


def get(url, headers=None):
    """Returns (status, body or None, final URL, attempts). status -1 means a network error."""
    check_url(url)
    hdrs = {"User-Agent": UA}
    hdrs.update(headers or {})
    for attempt in (1, 2):
        _pace()
        status, body, final = -1, None, url
        try:
            with _opener.open(urllib.request.Request(url, headers=hdrs), timeout=60) as r:
                body = r.read()
                status = r.status
                final = r.geturl()
        except urllib.error.HTTPError as e:
            status = e.code
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            status = -1
        if status == 429:
            raise Stop("HTTP 429 at " + url)
        failed = status == -1 or 500 <= status <= 599
        _count(failed, "%s -> %s" % (url, status))
        if failed and attempt == 1:
            continue
        return status, body, final, attempt


def ls_remote(repo_url, ref="HEAD"):
    """git ls-remote, paced like an HTTP request. Returns the SHA of ref."""
    check_url(repo_url)
    for attempt in (1, 2):
        _pace()
        p = subprocess.run(
            ["git", "-c", "http.userAgent=" + UA, "ls-remote", repo_url, ref],
            capture_output=True, text=True, timeout=120,
            env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin"})
        ok = p.returncode == 0 and p.stdout.strip()
        _count(not ok, "git ls-remote " + repo_url)
        if ok:
            return p.stdout.split()[0]
        if attempt == 2:
            raise Stop("git ls-remote failed twice for %s: %s" % (repo_url, p.stderr.strip()))
