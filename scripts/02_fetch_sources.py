#!/usr/bin/env python3
"""Step 2a: fetch the pinned metadata (one request at a time).

  - libretro/libretro-database: metadat/no-intro/Nintendo - Nintendo 64.dat at a pinned commit
  - libretro/libretro-thumbnails: README.md (file-name character rule; says the project moved)
  - libretro-thumbnails/libretro-thumbnails: README.md at its new home (same rule, checked twice)
  - libretro-thumbnails/Nintendo_-_Nintendo_64: recursive tree listing at a pinned commit
    (which Named_Boxarts files exist; avoids blind 404 probes of thumbnails.libretro.com)

Pin with DB_SHA, TH_SHA, TH2_SHA, N64_SHA to rebuild against the same revisions; otherwise HEAD.
A source already recorded in <out_dir>/src/sources.tsv with its file present is not fetched again.
Usage: 02_fetch_sources.py <out_dir>
"""
import datetime
import hashlib
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import net  # noqa: E402

DAT_PATH = "metadat/no-intro/Nintendo - Nintendo 64.dat"

SOURCES = [
    # (repository, pin env var, ls-remote URL, URL template, saved name, extra headers)
    ("libretro/libretro-database", "DB_SHA", "https://github.com/libretro/libretro-database",
     "https://raw.githubusercontent.com/libretro/libretro-database/{sha}/" + urllib.parse.quote(DAT_PATH),
     "Nintendo - Nintendo 64.dat", None),
    ("libretro/libretro-thumbnails", "TH_SHA", "https://github.com/libretro/libretro-thumbnails",
     "https://raw.githubusercontent.com/libretro/libretro-thumbnails/{sha}/README.md",
     "libretro-thumbnails-README.md", None),
    ("libretro-thumbnails/libretro-thumbnails", "TH2_SHA", "https://github.com/libretro-thumbnails/libretro-thumbnails",
     "https://raw.githubusercontent.com/libretro-thumbnails/libretro-thumbnails/{sha}/README.md",
     "libretro-thumbnails-new-README.md", None),
    ("libretro-thumbnails/Nintendo_-_Nintendo_64", "N64_SHA", "https://github.com/libretro-thumbnails/Nintendo_-_Nintendo_64",
     "https://api.github.com/repos/libretro-thumbnails/Nintendo_-_Nintendo_64/git/trees/{sha}?recursive=1",
     "n64-thumbnails-tree.json", {"Accept": "application/vnd.github+json"}),
]


def main():
    out = sys.argv[1]
    os.makedirs(out + "/src", exist_ok=True)
    os.makedirs(out + "/tmp", exist_ok=True)
    tsv = out + "/src/sources.tsv"
    done = set()
    if os.path.exists(tsv):
        done = {line.split("\t")[0] for line in open(tsv).read().splitlines()[1:]}
    else:
        with open(tsv, "w") as f:
            f.write("repository\tcommit\turl\thttp_status\tbytes\tsha256\tfetched_utc\n")

    for repo, env, remote, template, name, headers in SOURCES:
        if repo in done and os.path.exists(out + "/src/" + name):
            print("have", repo)
            continue
        sha = os.environ.get(env) or net.ls_remote(remote)
        url = template.format(sha=sha)
        status, body, _, _ = net.get(url, headers)
        if status != 200:
            sys.exit("fetch failed: %s %s" % (status, url))
        if name.endswith(".json") and json.loads(body).get("truncated"):
            sys.exit("tree listing truncated; use a blobless clone instead")
        tmp = out + "/tmp/" + name + ".part"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, out + "/src/" + name)
        row = (repo, sha, url, status, len(body), hashlib.sha256(body).hexdigest(),
               datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        with open(tsv, "a") as f:
            f.write("\t".join(str(x) for x in row) + "\n")
        print("\t".join(str(x) for x in row))


if __name__ == "__main__":
    try:
        main()
    except net.Stop as e:
        sys.exit("STOP: %s" % e)
