# Mupen64Plus-AE Turnip cover art

Box art for [Mupen64Plus-AE Turnip](https://github.com/pwnedbygary/mupen64plus-ae-turnip), an N64
emulator for Android that shows on the device as "M64P Turnip". When the app adds a game to its
library with **Download cover art** checked, or when another app opens a game that is not in the
library, the app downloads the game's picture from this repository over HTTPS, unless it already
has a picture for the game. Releases built before the app switched to this repository, release
V339 among them, get their cover art from another server.

## What is here

- `coverart/`: 491 PNG files, one for each cover-art name from the app's ROM database for which
  the set has a picture. The ROM database gives 854 names. Most of the 363 names without a
  picture belong to homebrew, hacks, copier BIOSes and Aleck64 games, few of which the No-Intro
  list names.
- `manifest.tsv`: for each file, the No-Intro name it was matched to, the URL it was downloaded
  from, its SHA-256 and its size.
- `missing.tsv`: the 363 names without a picture, and why, and two names that must stay absent:
  `dummy` (see "File names") and `.png`, which some homebrew entries would get and the app never
  asks for.
- `verification.tsv`: each file's Git blob hash, compared with the file in libretro's
  repository.
- `scripts/`: the scripts that built the set.
  `REPO=<a clone of mupen64plus-ae-turnip> sh scripts/rebuild.sh <empty folder>` runs them again.
  It reads the app's ROM database and the No-Intro list at the commits named below, downloads the
  pictures again from `thumbnails.libretro.com`, and checks each against libretro's commit named
  below. `verification.tsv` marks with FAIL any picture that libretro has changed since, and
  `rebuild.sh` still exits with status 0. A picture that libretro has removed is not marked
  FAIL: the name then gets the game's next picture in the order described below, or moves to
  `missing.tsv`. To see every change, compare the new `manifest.tsv` and `missing.tsv` with the
  ones here.

## Where the pictures come from

Each picture is a byte-for-byte copy of a file in libretro's Nintendo 64 thumbnails,
[libretro-thumbnails/Nintendo_-_Nintendo_64](https://github.com/libretro-thumbnails/Nintendo_-_Nintendo_64)
at commit `c2f9cd21605e45b4d9dc59375c942c54d3afe7e7`, downloaded from `thumbnails.libretro.com`
on 27 October 2026. The pictures are scans of game boxes, and their copyright belongs to the
games' publishers. libretro publishes them without a license, and this repository grants none.

To find each game's picture, the scripts match the MD5 checksums in the app's ROM database
(`mupen64plus.ini` at app commit `9bcca07a6`) with the No-Intro Nintendo 64 list in
[libretro-database](https://github.com/libretro/libretro-database) at commit
`25da22340889d04bd6e3a8c116d2750af4157d4f` (list version 2026.10.07), which libretro-database
imports from the [No-Intro](https://no-intro.org) project.

For each name, the set looks only at the game's retail entries in that list, or at its beta,
prototype, demo and kiosk entries when it has no retail one, and takes the first entry that has a
picture, trying USA first, then World, Europe and Japan. `manifest.tsv` names the picture chosen
and the ones tried. So 40 Winks has no picture: libretro has none for its only retail entry,
"40 Winks (USA) (Piko Interactive)", though it has one of a prototype.

## Names in the data files, and their licenses

Besides the scripts' own results, such as checksums, sizes, status codes and reasons, the three
`.tsv` files hold these names:

- No-Intro names, from the libretro-database list above: the `nointro_name`, `source_url` and
  `candidates_tried` columns of `manifest.tsv`, its `region` column, which is the first
  parenthesized part of `nointro_name`, and the `detail` column of `missing.tsv`. The names were
  selected and not otherwise changed, except in `source_url`, which writes them as libretro's
  file names (`&` replaced by `_` and `.png` added) encoded for a web address. libretro-database
  is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and these
  columns are shared under the same license.
- libretro's file names: the `same_bytes_as_libretro_file` column of `verification.tsv` gives,
  for each picture, the names of the files in libretro's repository that have the same bytes.
  All but two are names from the list above, written as file names in the same way, and are
  shared under the same license. The two others, `Dongwu Senlin (China) (iQue).png` and
  `Yueye Motuo (China) (iQue).png`, are libretro's own names for two iQue pictures and are not in
  the list.
- Names from the app's ROM database: the `artname` column of each file, made from the game's
  GoodName by the rule under "File names", and the `goodnames` column of `missing.tsv`. The ROM
  database, `mupen64plus.ini`, is part of Mupen64Plus and is licensed under GPL-2.0, as the app's
  [LICENSES.md](https://github.com/pwnedbygary/mupen64plus-ae-turnip/blob/master/LICENSES.md)
  says.

## File names

The app asks for `<name>.png`. It makes `<name>` from the game's GoodName in its ROM database:
the text before the first " (", trimmed, without `'`, `.` and `!`, and with each run of
characters other than A to Z, a to z, 0 to 9 and `_` turned into `_` (`RomDatabase.java` in the
app). Kiosk demos ask for the retail game's name. Do not add a file named `dummy`: the app asks
for that name for every game that it cannot identify in its database.
