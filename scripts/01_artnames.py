#!/usr/bin/env python3
"""Step 1: compute the cover-art names the app asks for.

Reproduces, for mupen64plus-ae-turnip at 9bcca07a60e6f7855169248f1542e7aa1b21ebc7:
  - ConfigFile.reload / ConfigSection(String, BufferedReader)  (persistent/ConfigFile.java:199-264, 352-451)
  - RomDatabase.setDatabaseFile                                 (util/RomDatabase.java:114-132)
  - RomDetail(ConfigSection)                                    (util/RomDatabase.java:233-295)
  - the fallback art names "dummy" (RomDatabase.java:149, 190) and
    details.get(0).artName (RomDatabase.java:151)

Usage: 01_artnames.py <mupen64plus.ini> <out_dir>
Writes <out_dir>/entries.tsv and <out_dir>/artnames.tsv.
"""
import re
import sys
from collections import OrderedDict

SECTIONLESS_NAME = "[<sectionless!>]"
HOMEBREW_CRC = "00000000 00000000"


def java_trim(s):
    """String.trim(): strips every char <= U+0020 at both ends."""
    i, j = 0, len(s)
    while i < j and s[i] <= " ":
        i += 1
    while j > i and s[j - 1] <= " ":
        j -= 1
    return s[i:j]


def read_lines(text):
    """BufferedReader.readLine(): terminators are \\n, \\r or \\r\\n; no empty line after a final terminator."""
    parts = re.split(r"\r\n|\r|\n", text)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def parse_config(text):
    """Returns (OrderedDict name -> {param: value}, stop_reason or None)."""
    lines = read_lines(text)
    pos = 0
    stop = None

    def read_section():
        nonlocal pos, stop
        params = {}
        while pos < len(lines):
            full = lines[pos]
            pos += 1
            s = java_trim(full)
            if len(s) < 1 or s.startswith("#") or s.startswith(";") or (len(s) > 1 and s.startswith("//")):
                continue
            if "=" in s:
                x = s.index("=")
                if x < 1:
                    stop = "line %d: '=' at column 0" % pos
                    return params, None
                if x < len(s) - 1:
                    p = java_trim(s[:x])
                    if len(p) < 1:
                        stop = "line %d: empty key" % pos
                        return params, None
                    v = java_trim(s[x + 1:])
                    if len(v) > 0:
                        params[p] = v  # a repeated key overwrites the value
                continue  # "param=" is ignored
            if "[" in s:
                if len(s) < 3 or "]" not in s:
                    stop = "line %d: bad section line" % pos
                    return params, None
                x = s.index("[")
                y = s.index("]")
                if y <= x + 1:
                    stop = "line %d: bad section line" % pos
                    return params, None
                return params, java_trim(s[x + 1:y])
            stop = "line %d: not a comment, parameter or section" % pos
            return params, None
        return params, None

    config = OrderedDict()
    params, next_name = read_section()
    config[SECTIONLESS_NAME] = params
    while next_name:  # TextUtils.isEmpty(nextName) ends the read, as in reload()
        name = next_name
        params, next_name = read_section()
        config[name] = params  # LinkedHashMap.put: a repeated name replaces the earlier section in place
    return config, stop


def art_name_from_goodname(good_name):
    """RomDatabase.java:247 and :250. The ini is ASCII, so Java's and ICU's \\W agree with [^A-Za-z0-9_]."""
    base = java_trim(good_name.split(" (")[0])
    art = re.sub(r"[^A-Za-z0-9_]+", "_", re.sub(r"['.!]", "", base)) + ".png"
    return base, art


def main():
    ini_path, out_dir = sys.argv[1], sys.argv[2]
    raw = open(ini_path, "rb").read()
    if any(b > 0x7F for b in raw):
        sys.exit("non-ASCII bytes in the ini: the \\W rule would need Android's ICU semantics; stop")
    config, stop = parse_config(raw.decode("ascii"))

    entries = []
    for name, params in config.items():
        if name == SECTIONLESS_NAME:
            continue
        crc = params.get("CRC")
        if crc == HOMEBREW_CRC:
            good_name = ""  # RomDatabase.java:239-240
        else:
            good_name = params.get("GoodName")  # RomDatabase.java:242
        notes = []
        if good_name is None:
            base, art = None, None  # RomDatabase.java:262-267
            notes.append("no-GoodName: artName null, art path '<dir>/null', never downloaded")
        else:
            base, art = art_name_from_goodname(good_name)
            if crc == HOMEBREW_CRC:
                notes.append("homebrew CRC 00000000 00000000: GoodName forced to '' so artName '.png'; "
                             "cached goodName is empty so CacheRomInfoService never downloads it")
        if crc is None:
            notes.append("no CRC: found by MD5 only (not in the CRC map)")
        ref = params.get("RefMD5")
        if ref:
            if ref not in config:
                notes.append("RefMD5 points to a missing section (only SaveType/Status/Players/Rumble affected)")
        raw_good = params.get("GoodName", "")
        if "(Kiosk" in raw_good:
            notes.append("Kiosk: only the wiki URL changes (RomDatabase.java:256); art name is the plain base name")
        entries.append(OrderedDict(
            md5=name, crc=crc or "", goodname=raw_good, goodname_used=good_name if good_name is not None else "",
            refmd5=ref or "", basename=base if base is not None else "", artname=art if art is not None else "",
            notes="; ".join(notes)))

    with open(out_dir + "/entries.tsv", "w") as f:
        cols = list(entries[0].keys())
        f.write("\t".join(cols) + "\n")
        for e in entries:
            f.write("\t".join(e[c] for c in cols) + "\n")

    arts = OrderedDict()
    for e in entries:
        key = e["artname"] if e["artname"] else "(null)"
        arts.setdefault(key, []).append(e)

    def requested(art):
        if art == "(null)":
            return "no"
        if art == ".png":
            return "no"
        return "yes"

    with open(out_dir + "/artnames.tsv", "w") as f:
        f.write("artname\trequested_by_app\tentries\tmd5s\tcrcs\tgoodnames\n")
        for art, es in sorted(arts.items()):
            f.write("\t".join([
                art, requested(art), str(len(es)),
                ",".join(e["md5"] for e in es),
                ",".join(sorted(set(e["crc"] for e in es if e["crc"]))),
                " | ".join(e["goodname"] for e in es)]) + "\n")
        f.write("dummy\tyes (ROMs not in the database, RomDatabase.java:149,190)\t0\t\t\t"
                "(sentinel; one shared local path for every unknown ROM: must stay absent)\n")

    lower = {}
    for art in arts:
        lower.setdefault(art.lower(), []).append(art)
    case_clashes = [v for v in lower.values() if len(v) > 1]

    print("parse stop reason:", stop or "none (read to end of file)")
    print("sections (database entries):", len(entries))
    print("entries with RefMD5:", sum(1 for e in entries if e["refmd5"]))
    print("entries without GoodName:", sum(1 for e in entries if not e["goodname"]))
    print("entries without CRC:", sum(1 for e in entries if not e["crc"]))
    print("homebrew CRC entries:", sum(1 for e in entries if e["crc"] == HOMEBREW_CRC))
    print("Kiosk entries:", sum(1 for e in entries if "(Kiosk" in e["goodname"]))
    print("distinct art names (incl. '.png'/'(null)'):", len(arts))
    print("distinct art names the app can request:", sum(1 for a in arts if requested(a) == "yes"))
    print("case-insensitive clashes:", case_clashes)


if __name__ == "__main__":
    main()
