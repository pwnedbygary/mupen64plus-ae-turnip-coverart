#!/usr/bin/env python3
"""Step 3b + 4: download one image per art name from thumbnails.libretro.com, one at a time.

For each art name the app can request (artnames.tsv), the candidates are plan.tsv's names in
order; names tagged (Beta)/(Proto)/(Demo)/(Kiosk) are used only when the art name has no other
name (brief, step 3). The first candidate answering 200 with an image is saved byte for byte as
coverart/<art name>; a 404 moves to the next candidate. Any other status stops the fallback for
that art name (recorded, so a re-run can retry it). net.Stop (429, three failures in a row) and
the 400 MB cap end the run; everything fetched so far stays recorded.

Re-runs skip art names already recorded as downloaded (file present, same sha256) or as missing
after 404s; pass --retry-missing to ask again for the missing ones.
Usage: 04_download.py <out_dir> [--retry-missing]
Writes manifest.tsv, missing.tsv, logs/requests.tsv, logs/state.json.
"""
import csv
import datetime
import difflib
import hashlib
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import net  # noqa: E402

LIMIT = 400 * 1000 * 1000


def read_tsv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def image_info(body):
    if body[:8] == b"\x89PNG\r\n\x1a\n" and body[12:16] == b"IHDR":
        w, h = struct.unpack(">II", body[16:24])
        return "png", "%dx%d" % (w, h)
    if body[:3] == b"\xff\xd8\xff":
        return "jpeg", ""
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", ""
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp", ""
    return "", ""


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    out = sys.argv[1]
    retry_missing = "--retry-missing" in sys.argv[2:]
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    os.makedirs(out + "/coverart", exist_ok=True)
    os.makedirs(out + "/logs", exist_ok=True)
    os.makedirs(out + "/tmp", exist_ok=True)

    arts = [a for a in read_tsv(out + "/artnames.tsv")
            if a["requested_by_app"] == "yes" and a["artname"] != "dummy"]
    all_arts = arts
    if only:
        arts = [a for a in arts if a["artname"] == only]
    plan = {}
    for r in read_tsv(out + "/plan.tsv"):
        plan.setdefault(r["artname"], []).append(r)

    state_path = out + "/logs/state.json"
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    req_log = open(out + "/logs/requests.tsv", "a")
    if req_log.tell() == 0:
        req_log.write("utc\tartname\tnointro_name\turl\thttp_status\tattempts\tbytes\tcontent_type\n")

    total = sum(s["bytes"] for s in state.values() if s.get("result") == "ok")
    stop_reason = None
    try:
        for a in arts:
            art = a["artname"]
            s = state.get(art)
            if s and s.get("result") == "ok":
                path = out + "/coverart/" + art
                if os.path.exists(path) and hashlib.sha256(open(path, "rb").read()).hexdigest() == s["sha256"]:
                    continue
            if s and s.get("result") in ("missing", "unmatched") and not retry_missing:
                continue
            rows = plan.get(art, [])
            if not rows:
                state[art] = dict(result="unmatched", tried=[])
                continue
            retail = [r for r in rows if r["skip_tag"] == "no"]
            use = retail if retail else rows
            held_back = [r["nointro_name"] for r in rows if r["skip_tag"] == "yes"] if retail else []
            tried = []
            result = None
            for r in use:
                status, body, final, attempts = net.get(r["url"])
                kind, dims = image_info(body) if (status == 200 and body) else ("", "")
                req_log.write("\t".join([now(), art, r["nointro_name"], r["url"], str(status), str(attempts),
                                         str(len(body) if body else 0), kind]) + "\n")
                req_log.flush()
                tried.append([r["nointro_name"], status if (status != 200 or kind) else "200-not-image"])
                if status == 200 and kind:
                    if total + len(body) > LIMIT:
                        raise net.Stop("the set would pass 400 MB at %s (%d + %d bytes)" % (art, total, len(body)))
                    tmp = out + "/tmp/" + art + ".part"
                    with open(tmp, "wb") as f:
                        f.write(body)
                    os.replace(tmp, out + "/coverart/" + art)
                    total += len(body)
                    result = dict(result="ok", nointro=r["nointro_name"], region=r["region"], url=r["url"],
                                  final_url=final, status=status, sha256=hashlib.sha256(body).hexdigest(),
                                  bytes=len(body), dims=dims, kind=kind, tree_mode=r["tree_mode"],
                                  rank=r["rank"], tried=tried, utc=now())
                    break
                if status == 404 or (status == 200 and not kind):
                    continue
                result = dict(result="error", tried=tried, utc=now())
                break
            if result is None:
                result = dict(result="missing", tried=tried, held_back=held_back, utc=now())
            state[art] = result
            with open(state_path + ".part", "w") as f:
                json.dump(state, f, indent=1, sort_keys=True)
            os.replace(state_path + ".part", state_path)
    except net.Stop as e:
        stop_reason = str(e)
    finally:
        req_log.close()
        with open(state_path + ".part", "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
        os.replace(state_path + ".part", state_path)

    write_outputs(out, all_arts, plan, state, stop_reason)
    print("downloaded:", sum(1 for s in state.values() if s["result"] == "ok"),
          "| total bytes:", total, "| stop:", stop_reason or "none")
    if stop_reason:
        sys.exit("STOP: " + stop_reason)


def similar_titles(out):
    """For unmatched art names with a GoodN64 [!] dump: No-Intro titles that look like the same game."""
    txt = open(out + "/src/Nintendo - Nintendo 64.dat", encoding="utf-8").read()
    names = sorted({n for n in re.findall(r'^\tname "(.*)"$', txt, re.M) if n != "Nintendo - Nintendo 64"})
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    titles = {}
    for n in names:
        titles.setdefault(norm(n.split(" (")[0]), []).append(n)

    def hint(goodnames):
        if "[!]" not in goodnames:
            return ""
        base = norm(goodnames.split(" | ")[0].split(" (")[0])
        found = []
        for t, ns in titles.items():
            if t == base or (len(t) > 6 and (t in base or base in t)) or difflib.SequenceMatcher(None, t, base).ratio() >= 0.9:
                found += ns
        return ("similar No-Intro title(s) with a different checksum, not used: " + "; ".join(found)) if found else \
            "GoodN64 [!] dump; no similar No-Intro title"
    return hint


def write_outputs(out, arts, plan, state, stop_reason):
    unmatched = {}
    for e in read_tsv(out + "/unmatched.tsv"):
        unmatched.setdefault(e["artname"], []).append(e)
    hint = similar_titles(out)
    with open(out + "/manifest.tsv", "w") as f:
        f.write("artname\tnointro_name\tregion\tsource_url\thttp_status\tsha256\tbytes\twidth_x_height"
                "\tformat\tcandidate_rank\ttree_mode\tcandidates_tried\n")
        for a in arts:
            s = state.get(a["artname"])
            if not s or s["result"] != "ok":
                continue
            f.write("\t".join([a["artname"], s["nointro"], s["region"], s["url"], str(s["status"]), s["sha256"],
                               str(s["bytes"]), s["dims"], s["kind"], s["rank"],
                               "symlink" if s["tree_mode"] == "120000" else ("file" if s["tree_mode"] else "not in tree"),
                               "; ".join("%s=%s" % (n, st) for n, st in s["tried"])]) + "\n")
    with open(out + "/missing.tsv", "w") as f:
        f.write("artname\treason\tdetail\tentries\tgoodnames\n")
        for a in arts:
            s = state.get(a["artname"])
            if s and s["result"] == "ok":
                continue
            if not s:
                reason, detail = "not attempted", "run stopped before this art name: " + (stop_reason or "")
            elif s["result"] == "unmatched":
                reason = "no database entry for this art name has an MD5 in the No-Intro dat"
                detail = "all %d entries unmatched" % len(unmatched.get(a["artname"], []))
                h = hint(a["goodnames"])
                if h:
                    detail += " | " + h
            elif s["result"] == "missing":
                reason = "No-Intro name(s) found but thumbnails.libretro.com has no image for them"
                detail = "; ".join("%s=%s" % (n, st) for n, st in s["tried"])
                if s.get("held_back"):
                    detail += " | not tried (Beta/Proto/Demo/Kiosk while a retail name exists): " + "; ".join(s["held_back"])
            else:
                reason = "HTTP error; fallback stopped, re-run to retry"
                detail = "; ".join("%s=%s" % (n, st) for n, st in s["tried"])
            f.write("\t".join([a["artname"], reason, detail, a["entries"], a["goodnames"]]) + "\n")
        f.write("dummy\tsentinel art name for ROMs not in the database (RomDatabase.java:149,190); "
                "must stay absent\t\t0\t\n")
        homebrew = [a for a in read_tsv(out + "/artnames.tsv") if a["artname"] == ".png"]
        f.write(".png\thomebrew entries (CRC 00000000 00000000) get GoodName \"\" (RomDatabase.java:239-240) "
                "and so art name \".png\"; never requested (empty cached goodName)\t\t%s\t\n"
                % (homebrew[0]["entries"] if homebrew else "0"))


if __name__ == "__main__":
    main()
