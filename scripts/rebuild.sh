#!/bin/sh
# Rebuilds the cover-art set against the revisions pinned on 27 Oct 2026.
# Usage: scripts/rebuild.sh [out_dir]   (default: the folder above scripts/)
# A fresh build: run it on an empty out_dir; re-runs reuse what is already recorded and fetch nothing again.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-$(dirname "$here")}
repo=${REPO:?set REPO to a clone of https://github.com/pwnedbygary/mupen64plus-ae-turnip}
app_commit=9bcca07a60e6f7855169248f1542e7aa1b21ebc7

export DB_SHA=${DB_SHA:-25da22340889d04bd6e3a8c116d2750af4157d4f}
export TH_SHA=${TH_SHA:-5e5b12fa7bb0f98e98aa4d0dffb784735639ea84}
export TH2_SHA=${TH2_SHA:-aad29ecffc3b59b5ca1b1400fc6e6f2cd2addc70}
export N64_SHA=${N64_SHA:-c2f9cd21605e45b4d9dc59375c942c54d3afe7e7}

mkdir -p "$out/src" "$out/tmp" "$out/coverart" "$out/logs"
export TMPDIR="$out/tmp"
export PYTHONDONTWRITEBYTECODE=1

nice -n 19 git -C "$repo" show "$app_commit:app/src/main/java/paulscode/android/mupen64plusae/util/RomDatabase.java" > "$out/src/RomDatabase.java"
nice -n 19 git -C "$repo" show "$app_commit:app/src/main/assets/mupen64plus_data/mupen64plus.ini" > "$out/src/mupen64plus.ini"

nice -n 19 python3 "$here/01_artnames.py" "$out/src/mupen64plus.ini" "$out"
nice -n 19 python3 "$here/02_fetch_sources.py" "$out"
nice -n 19 python3 "$here/03_match.py" "$out"
nice -n 19 python3 "$here/04_download.py" "$out"
nice -n 19 python3 "$here/05_report.py" "$out"
