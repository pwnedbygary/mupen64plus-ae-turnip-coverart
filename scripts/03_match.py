#!/usr/bin/env python3
"""Step 2b + 3a: match database entries to No-Intro names and plan one image per art name.

Inputs (from steps 1 and 2a): entries.tsv, artnames.tsv, src/Nintendo - Nintendo 64.dat,
src/n64-thumbnails-tree.json.
Outputs: matches.tsv (entry -> No-Intro name), unmatched.tsv, plan.tsv (art name -> ordered
candidates). Prints the checksum verification on known entries.

Candidate order for one art name (brief, step 3): names tagged (Beta), (Proto), (Demo) or
(Kiosk) last; then region USA, World, Europe, Japan, any other (first parenthetical group of the
No-Intro name; a multi-region group takes its best region); then fewer extra tags; then name.
Usage: 03_match.py <out_dir>
"""
import collections
import csv
import json
import re
import sys
import urllib.parse

SKIP_TAG = re.compile(r"^(Beta|Proto|Demo|Kiosk)\b")
REGION_RANK = {"USA": 0, "World": 1, "Europe": 2, "Japan": 3}
BAD_CHARS = '&*/:`<>?\\|"'  # libretro-thumbnails README (both copies; the newer adds '"')
BASE_URL = "https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%2064/Named_Boxarts/"

KNOWN = [  # (database GoodName, No-Intro name expected from the published dumps)
    ("Super Mario 64 (U) [!]", "Super Mario 64 (USA)"),
    ("007 - The World is Not Enough (U) [!]", "007 - The World Is Not Enough (USA)"),
    ("Mario Kart 64 (U) [!]", "Mario Kart 64 (USA)"),
    ("Legend of Zelda, The - Ocarina of Time (U) (V1.0) [!]", "Legend of Zelda, The - Ocarina of Time (USA)"),
    ("GoldenEye 007 (U) [!]", "GoldenEye 007 (USA)"),
]


def read_tsv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def parse_dat(path):
    txt = open(path, encoding="utf-8").read()
    roms = []
    for block in re.findall(r"^game \((.*?)^\)", txt, re.M | re.S):
        name = re.search(r'^\tname "(.*)"$', block, re.M).group(1)
        region = re.search(r'^\tregion "(.*)"$', block, re.M)
        for rom in re.findall(r"^\trom \((.*)\)$", block, re.M):
            fields = dict(re.findall(r'(\w+) ("[^"]*"|\S+)', rom))
            fields = {k: v.strip('"') for k, v in fields.items()}
            roms.append(dict(game=name, region=region.group(1) if region else "",
                             rom=fields["name"], ext=fields["name"].rsplit(".", 1)[-1],
                             crc=fields.get("crc", "").upper(), md5=fields.get("md5", "").upper(),
                             sha1=fields.get("sha1", "").upper(), size=fields.get("size", "")))
    return roms


def thumb_name(nointro):
    return "".join("_" if c in BAD_CHARS else c for c in nointro) + ".png"


def groups(nointro):
    return re.findall(r"\(([^()]*)\)", nointro)


def region_of(nointro):
    g = groups(nointro)
    return g[0] if g else ""


def sort_key(nointro):
    g = groups(nointro)
    skip = any(SKIP_TAG.match(t) for t in g)
    regions = [r.strip() for r in (g[0].split(",") if g else [])]
    rank = min([REGION_RANK.get(r, 4) for r in regions] or [4])
    return (skip, rank, len(g), nointro)


def main():
    out = sys.argv[1]
    entries = read_tsv(out + "/entries.tsv")
    roms = parse_dat(out + "/src/Nintendo - Nintendo 64.dat")
    by_md5 = collections.defaultdict(list)
    for r in roms:
        by_md5[r["md5"]].append(r)
    tree = json.load(open(out + "/src/n64-thumbnails-tree.json"))
    boxarts = {it["path"][len("Named_Boxarts/"):]: it for it in tree["tree"]
               if it["path"].startswith("Named_Boxarts/") and it["type"] == "blob"}

    print("dat games/rom rows:", len({r["game"] for r in roms}), len(roms),
          "(z64 rows %d, v64 rows %d)" % (sum(r["ext"] == "z64" for r in roms), sum(r["ext"] == "v64" for r in roms)))

    # Checksum verification on known entries.
    by_good = {e["goodname"]: e for e in entries}
    print("checksum verification (database MD5 vs the dat's md5 / crc fields):")
    for good, expect in KNOWN:
        e = by_good[good]
        hits = by_md5.get(e["md5"], [])
        same_game = [r for r in roms if r["game"] == expect]
        crc_hit = [r for r in same_game if r["crc"] in e["crc"].split()]
        print("  %-56s md5 %s -> %s | header CRC %s in dat crc: %s" % (
            good, e["md5"], [(r["game"], r["ext"]) for r in hits] or "NO MATCH", e["crc"], bool(crc_hit)))
        assert any(r["game"] == expect and r["ext"] == "z64" for r in hits), good

    matches, unmatched = [], []
    ext_count = collections.Counter()
    for e in entries:
        hits = by_md5.get(e["md5"].upper(), [])
        if hits:
            for r in hits:
                ext_count[r["ext"]] += 1
                matches.append((e, r))
        else:
            unmatched.append(e)

    with open(out + "/matches.tsv", "w") as f:
        f.write("md5\tcrc\tgoodname\tartname\tnointro_name\tdat_region\tdat_rom\tdat_crc32\n")
        for e, r in matches:
            f.write("\t".join([e["md5"], e["crc"], e["goodname"], e["artname"], r["game"], r["region"], r["rom"], r["crc"]]) + "\n")
    with open(out + "/unmatched.tsv", "w") as f:
        f.write("md5\tcrc\tgoodname\tartname\treason\n")
        for e in unmatched:
            f.write("\t".join([e["md5"], e["crc"], e["goodname"], e["artname"],
                               "MD5 not in the No-Intro dat (bad dump, hack, trainer, translation, overdump or other non-No-Intro dump)"]) + "\n")

    # Plan: candidates per requested art name.
    cands = collections.defaultdict(set)
    for e, r in matches:
        if e["artname"] and e["artname"] != ".png":
            cands[e["artname"]].add(r["game"])
    arts = [a for a in read_tsv(out + "/artnames.tsv") if a["requested_by_app"] == "yes" and a["artname"] != "dummy"]
    with open(out + "/plan.tsv", "w") as f:
        f.write("artname\trank\tnointro_name\tregion\tskip_tag\tthumb_file\tin_tree\ttree_mode\ttree_size\turl\n")
        for a in arts:
            names = sorted(cands.get(a["artname"], ()), key=sort_key)
            for i, n in enumerate(names, 1):
                tf = thumb_name(n)
                it = boxarts.get(tf)
                f.write("\t".join([a["artname"], str(i), n, region_of(n), "yes" if sort_key(n)[0] else "no",
                                   tf, "yes" if it else "no",
                                   it["mode"] if it else "", str(it.get("size", "")) if it else "",
                                   BASE_URL + urllib.parse.quote(tf)]) + "\n")
    planned = [a["artname"] for a in arts]
    with_cands = [a for a in planned if cands.get(a)]
    first_in_tree = 0
    any_in_tree = 0
    est = 0
    for a in with_cands:
        names = sorted(cands[a], key=sort_key)
        present = [n for n in names if thumb_name(n) in boxarts]
        if present:
            any_in_tree += 1
            it = boxarts[thumb_name(present[0])]
            est += it.get("size", 0) if it["mode"] == "100644" else 0
        if thumb_name(names[0]) in boxarts:
            first_in_tree += 1
    print("entries matched / unmatched:", len({e["md5"] for e, _ in matches}), len(unmatched))
    print("matched rows by dat extension:", dict(ext_count))
    print("requested art names:", len(planned), "| with >=1 No-Intro name:", len(with_cands),
          "| first choice in tree:", first_in_tree, "| any choice in tree:", any_in_tree)
    print("size estimate of chosen regular files in the tree (symlinks not counted): %.1f MB" % (est / 1e6))


if __name__ == "__main__":
    main()
