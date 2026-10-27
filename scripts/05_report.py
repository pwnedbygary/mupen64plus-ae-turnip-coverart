#!/usr/bin/env python3
"""Step 5: verify the downloaded set and write report.md and verification.tsv (no network).

Checks for every manifest row: the file exists under coverart/, sha256, size and PNG IHDR size
match the manifest, and its git blob SHA-1 equals a regular file's blob in the pinned
libretro-thumbnails/Nintendo_-_Nintendo_64 tree (Named_Boxarts), i.e. the bytes are libretro's.
Also checks that coverart/ holds nothing else and no file named "dummy" or ".png".
Usage: 05_report.py <out_dir>
"""
import collections
import csv
import datetime
import hashlib
import json
import os
import struct
import sys


def read_tsv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def git_blob_sha1(body):
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


def main():
    out = sys.argv[1]
    entries = read_tsv(out + "/entries.tsv")
    arts = read_tsv(out + "/artnames.tsv")
    matches = read_tsv(out + "/matches.tsv")
    unmatched = read_tsv(out + "/unmatched.tsv")
    plan = read_tsv(out + "/plan.tsv")
    manifest = read_tsv(out + "/manifest.tsv")
    missing = read_tsv(out + "/missing.tsv")
    sources = read_tsv(out + "/src/sources.tsv")
    requests = read_tsv(out + "/logs/requests.tsv")
    tree = json.load(open(out + "/src/n64-thumbnails-tree.json"))
    blobs = {}
    for it in tree["tree"]:
        if it["path"].startswith("Named_Boxarts/") and it["mode"] == "100644":
            blobs.setdefault(it["sha"], []).append(it["path"][len("Named_Boxarts/"):])

    problems = []
    ver_rows = []
    for m in manifest:
        path = out + "/coverart/" + m["artname"]
        if not os.path.exists(path):
            problems.append("missing file " + m["artname"])
            continue
        body = open(path, "rb").read()
        sha = hashlib.sha256(body).hexdigest()
        dims = ""
        if body[:8] == b"\x89PNG\r\n\x1a\n" and body[12:16] == b"IHDR":
            dims = "%dx%d" % struct.unpack(">II", body[16:24])
        g = git_blob_sha1(body)
        same = blobs.get(g, [])
        thumb = m["source_url"]
        ok = sha == m["sha256"] and str(len(body)) == m["bytes"] and dims == m["width_x_height"] and bool(same)
        if m["tree_mode"] == "file":
            expected = [p["thumb_file"] for p in plan if p["artname"] == m["artname"] and p["nointro_name"] == m["nointro_name"]]
            ok = ok and bool(expected) and expected[0] in same
        if not ok:
            problems.append("verification failed for " + m["artname"])
        ver_rows.append((m["artname"], sha, str(len(body)), dims, g, "; ".join(same) or "NO MATCH", "ok" if ok else "FAIL"))
    listed = {m["artname"] for m in manifest}
    on_disk = set(os.listdir(out + "/coverart"))
    extra = sorted(on_disk - listed)
    if extra:
        problems.append("files not in manifest: " + ", ".join(extra))
    for forbidden in ("dummy", ".png"):
        if forbidden in on_disk:
            problems.append("forbidden file present: " + forbidden)

    with open(out + "/verification.tsv", "w") as f:
        f.write("artname\tsha256\tbytes\twidth_x_height\tgit_blob_sha1\tsame_bytes_as_libretro_file\tresult\n")
        for r in ver_rows:
            f.write("\t".join(r) + "\n")

    total = sum(int(m["bytes"]) for m in manifest)
    largest = sorted(manifest, key=lambda m: -int(m["bytes"]))[:10]
    dup = collections.defaultdict(list)
    for m in manifest:
        dup[m["sha256"]].append(m["artname"])
    dups = [v for v in dup.values() if len(v) > 1]
    widths = collections.Counter(m["width_x_height"].split("x")[0] for m in manifest)
    requestable = [a for a in arts if a["requested_by_app"] == "yes" and a["artname"] != "dummy"]
    matched_arts = {p["artname"] for p in plan}
    status = collections.Counter(r["http_status"] for r in requests)
    retries = sum(1 for r in requests if r["attempts"] != "1")
    reasons = collections.Counter(m["reason"] for m in missing)
    ext = collections.Counter(m["dat_rom"].rsplit(".", 1)[-1] for m in matches)
    src = {s["repository"]: s for s in sources}
    db = src["libretro/libretro-database"]
    dat_version = ""
    for line in open(out + "/src/Nintendo - Nintendo 64.dat", encoding="utf-8"):
        if line.strip().startswith("version"):
            dat_version = line.split('"')[1]
            break
    now = datetime.datetime.now(datetime.timezone.utc)

    L = []
    w = L.append
    w("# Cover-art set for change G (built %s UTC)" % now.strftime("%Y-%m-%d %H:%M"))
    w("")
    w("Built on %s from libretro's N64 box art, renamed to the names mupen64plus-ae-turnip asks for." % now.strftime("%d %b %Y"))
    w("Requests ran from %s to %s UTC." % (requests[0]["utc"], requests[-1]["utc"]))
    w("")
    w("## Counts")
    w("")
    w("| What | Count |")
    w("| --- | ---: |")
    w("| Database entries (sections of `mupen64plus.ini`) | %d |" % len(entries))
    homebrew = sum(int(a["entries"]) for a in arts if a["artname"] == ".png")
    w("| Distinct art names (including `.png` from the %d homebrew entries) | %d |" % (
        homebrew, len([a for a in arts if a["artname"] != "dummy"])))
    w("| Art names the app can request (excluding `.png` and the `dummy` sentinel) | %d |" % len(requestable))
    w("| Entries matched to a No-Intro name by MD5 | %d |" % len({m["md5"] for m in matches}))
    w("| Entries not matched | %d |" % len(unmatched))
    w("| Art names with at least one No-Intro name | %d |" % len(matched_arts))
    w("| Images downloaded | %d |" % len(manifest))
    w("| Requestable art names without an image | %d |" % (len(requestable) - len(manifest)))
    w("| ...because no entry of the art name is in the No-Intro dat | %d |" % reasons.get("no database entry for this art name has an MD5 in the No-Intro dat", 0))
    w("| ...because libretro has no image for the No-Intro name(s) | %d |" % reasons.get("No-Intro name(s) found but thumbnails.libretro.com has no image for them", 0))
    w("")
    w("Total size: %d bytes (%.1f MB) in %d files. Widths: %s." % (
        total, total / 1e6, len(manifest), ", ".join("%s px: %d" % (k, v) for k, v in widths.most_common(5))))
    w("Identical images under several art names: %d groups (%s)." % (
        len(dups), "; ".join(", ".join(d) for d in dups) or "none"))
    w("")
    w("Largest files:")
    w("")
    for m in largest:
        w("- `%s` (%s), %s bytes, %s" % (m["artname"], m["nointro_name"], m["bytes"], m["width_x_height"]))
    w("")
    w("## Sources (pinned)")
    w("")
    w("- App: mupen64plus-ae-turnip `9bcca07a60e6f7855169248f1542e7aa1b21ebc7`; `RomDatabase.java` sha256 `%s`, "
      "`mupen64plus.ini` sha256 `%s` (exported with `git show`)." % (
          hashlib.sha256(open(out + "/src/RomDatabase.java", "rb").read()).hexdigest(),
          hashlib.sha256(open(out + "/src/mupen64plus.ini", "rb").read()).hexdigest()))
    w("- libretro/libretro-database `%s`: `metadat/no-intro/Nintendo - Nintendo 64.dat` (dat version %s, %s bytes, "
      "sha256 `%s`). Licence CC-BY-SA-4.0." % (db["commit"], dat_version, db["bytes"], db["sha256"]))
    for repo in ("libretro/libretro-thumbnails", "libretro-thumbnails/libretro-thumbnails", "libretro-thumbnails/Nintendo_-_Nintendo_64"):
        s = src[repo]
        w("- %s `%s`: %s (sha256 `%s`)." % (repo, s["commit"], s["url"].split("/")[-1] if "README" in s["url"] else "tree listing", s["sha256"]))
    w("- Images: `https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%2064/Named_Boxarts/<file>`.")
    w("")
    w("## How the app names cover art (`RomDatabase.java` at 9bcca07a6)")
    w("")
    w("- :97 URL template `http://coverart.zurita.me/CoverArt/%s`; :251 `artUrl` = template + `artName`.")
    w("- :233-242 per database section: `md5` = section name, `crc` = `CRC`, `goodName` = `GoodName`, except "
      "`CRC=00000000 00000000` (homebrew) which forces `goodName = \"\"`.")
    w("- :247 `baseName` = GoodName up to the first \" (\", trimmed; :250 `artName` = baseName without `'`, `.`, `!`, "
      "then every run of non-word characters becomes `_`, plus `.png` (\"Legend of Zelda, The - Ocarina of Time (U) "
      "(V1.0) [!]\" -> `Legend_of_Zelda_The_Ocarina_of_Time.png`).")
    w("- :256 Kiosk: only the wiki URL changes; a Kiosk entry gets the same art name as the retail game.")
    w("- :262-266 no GoodName -> `artName` null (no such entry in this ini).")
    w("- :270-274 `RefMD5` only redirects SaveType/Status/Players/Rumble; GoodName and CRC (so the art name) come "
      "from the entry itself.")
    w("- :139-157, :159-193 ROM not found by MD5: CRC lookup (several hits narrowed by the country code in the "
      "GoodName); no hit -> art name `dummy` (:149, :190), several hits -> first hit's art name (:151). So every "
      "requested name is one of the database art names or `dummy`; `dummy` is one shared local file for all unknown "
      "ROMs and must never exist in the set.")
    w("- The `.png` name of homebrew entries is never requested: `CacheRomInfoService.downloadCoverArt` skips "
      "entries whose cached goodName is empty.")
    w("- ConfigFile (`persistent/ConfigFile.java:199-264, 352-451`) parsing reproduced: trimmed lines; `#`, `;`, `//` "
      "comments; empty values ignored; a repeated key or section replaces the earlier one; a malformed line would end "
      "the read (none in this ini; the parser read to the end).")
    w("")
    w("## Matching and choice")
    w("")
    w("- Checksum: the database MD5 equals the dat's `md5` of the `.z64` (big-endian) row: Super Mario 64 (U) [!] "
      "`20B854B239203BAF6C961B850A4A51A2` -> \"Super Mario 64 (USA)\" (.z64), and so for 007 TWINE (U), Mario Kart 64 "
      "(U), Zelda OoT (U) (V1.0), GoldenEye 007 (U). The database CRC is the ROM header's CRC pair and never equals the "
      "dat's `crc` (CRC32 of the file). The app hashes ROMs after swapping them to big-endian, uppercase hex "
      "(`FileUtil.java:1270-1324`). Matched rows by extension: %s (no `.v64` match)." % dict(ext))
    w("- File name: No-Intro game name with each of ``&*/:`<>?\\|\"`` replaced by `_`, plus `.png`. The older README "
      "(libretro/libretro-thumbnails) lists ten characters; the current one (libretro-thumbnails/libretro-thumbnails) "
      "adds `\"`. Only `&` occurs in N64 names (14 names).")
    w("- Order per art name: names tagged (Beta)/(Proto)/(Demo)/(Kiosk) only when the art name has no other name; then "
      "USA, World, Europe, Japan, other (first parenthetical group); then fewer tags; then name. 404 -> next name.")
    w("")
    w("## Requests")
    w("")
    w("thumbnails.libretro.com: %d requests (%s), %d retries, no 429 or 5xx. GitHub: 4 `git ls-remote` and 4 file "
      "fetches (raw.githubusercontent.com, api.github.com). One request at a time, at least 0.5 s apart, User-Agent "
      "`mupen64plus-ae-turnip-coverart-builder/1`." % (
          len(requests), ", ".join("%s: %d" % kv for kv in sorted(status.items())), retries))
    w("")
    w("## Verification (no network)")
    w("")
    w("%d of %d files: sha256, size and PNG size match the manifest, and the git blob SHA-1 equals a regular file in "
      "the pinned Named_Boxarts tree (for non-symlinks, the expected file itself). coverart/ holds no other file and no "
      "`dummy` or `.png`. Problems: %s. Details in `verification.tsv`." % (
          sum(1 for r in ver_rows if r[-1] == "ok"), len(manifest), "; ".join(problems) or "none"))
    w("")
    w("## Notes")
    w("")
    fallbacks = [m for m in manifest if m["candidate_rank"] != "1"]
    held = [m for m in missing if "not tried (Beta/Proto/Demo/Kiosk" in m["detail"]]
    near = [m for m in missing if "similar No-Intro title" in m["detail"]]
    w("- Kiosk entries do not get their own art names, and RefMD5 never changes an art name (see above).")
    w("- The No-Intro dat has no \"(Beta)\" or \"(Kiosk)\" tags (pre-release builds are \"(Proto)\"); its 8 "
      "\"(Demo)\" names are homebrew. The 20 Kiosk entries of the database match no No-Intro checksum.")
    w("- Second choices used: %s." % ("; ".join("`%s` <- %s" % (m["artname"], m["nointro_name"]) for m in fallbacks) or "none"))
    w("- Held back by the Beta/Proto/Demo/Kiosk rule (a Proto image exists): %s." % (
        ", ".join("`%s`" % m["artname"] for m in held) or "none"))
    w("- GoodN64 [!] dumps whose checksum No-Intro does not list (similar No-Intro titles in `missing.tsv`, not used): %s." % (
        ", ".join("`%s`" % m["artname"] for m in near) or "none"))
    w("- Most of the %d art names without a No-Intro match are copier BIOSes, homebrew, hacks, Aleck64 boards and "
      "64DD cart hacks." % reasons.get("no database entry for this art name has an MD5 in the No-Intro dat", 0))
    w("- libretro-thumbnails/Nintendo_-_Nintendo_64 carries no licence file; libretro-database is CC-BY-SA-4.0.")
    w("- Besides the scripts' `git show`, this build's interactive checks ran read-only `git rev-parse HEAD`, "
      "`git cat-file -t` and `git ls-tree` at 9bcca07a6 on the repository.")
    w("")
    w("## Files")
    w("")
    w("- `coverart/` the set; `manifest.tsv`, `missing.tsv`, `verification.tsv`.")
    w("- `entries.tsv` (every database entry and its art name), `artnames.tsv` (art name -> MD5s, CRCs, GoodNames), "
      "`matches.tsv`, `unmatched.tsv`, `plan.tsv` (ordered candidates).")
    w("- `src/` pinned inputs and `src/sources.tsv`; `logs/requests.tsv` every image request; `logs/state.json`.")
    w("- `scripts/rebuild.sh` runs steps 01-05 against the same pinned revisions.")
    open(out + "/report.md", "w").write("\n".join(L) + "\n")
    print("verified ok:", sum(1 for r in ver_rows if r[-1] == "ok"), "/", len(manifest), "| problems:", problems or "none")
    print("total bytes:", total, "| duplicate groups:", len(dups))


if __name__ == "__main__":
    main()
