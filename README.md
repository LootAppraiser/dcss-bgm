# dcss-bgm

A tool and a mapping for **background music in DCSS Webtiles**, through [DWEM](https://github.com/refracta/dcss-webtiles-extension-module)'s
SoundSupport. It plays a different track for each branch and depth, with triggers for starting a game, holding the
Orb and game over.

**This repo contains no audio, and never will.** You bring your own music files, build a pack from them on your own
computer, and load it into your browser. Nothing is uploaded or shared. (`audio/`, `build/`, zips and every audio
extension are git-ignored; do not `git add -f` them.)

## Use it

1. Put your tracks in a folder (or point the tool at one you already have, e.g. `~/Music/MyGame`).
2. Edit [`mapping.csv`](mapping.csv): which track plays where. Missing files are simply skipped, so a partial pack works.
3. Build:
   ```
   python3 tools/build_pack.py --audio ~/Music/MyGame
   ```
   It converts non-MP3 files to Ogg Opus (needs `ffmpeg`; `.mp3` files are kept as they are), writes the DWEM
   `init.txt`, zips everything into `build/dcss-bgm.zip`, and checks the result the way DWEM reads it.
4. In the game (with DWEM and its SoundSupport running), open the chat and run `/SoundSupport register`, then pick
   `build/dcss-bgm.zip`. The pack is stored in that browser profile only.
5. Add this line to your rc (next to your other `sound_pack` lines) and set a volume you like:
   ```
   sounds_on = true
   sound_pack += local://dcss-bgm.zip
   bgm_volume = 0.4
   ```
6. Start or reload a game. `/SoundSupport list` shows registered packs; `/SoundSupport reload` re-reads them;
   after rebuilding, `/SoundSupport remove local://dcss-bgm.zip`, register the new zip, and reload.

## Mixing with the packs you already use

DWEM merges the `dwem_bgm` lines from **every** pack in your rc into one list. When you arrive at a place or depth,
it takes all entries that match (from all packs) and makes one weighted random pick. So this pack mixes with, for
example, the DCSS UST pack by default, and `weight` in `mapping.csv` sets the split:

| your weight | share of the picks for that place, if the other pack's weights for it add up to 1 |
|---|---|
| 0.43 | 30% |
| 1 | 50% |
| 2 | 67% |
| 3 | 75% |
| 9 | 90% |

(UST's weights for a place add up to 1 almost everywhere; its Dungeon is 0.7 + 0.15 + 0.15, Zot 0.6 + 0.4.)
Only want your music for some places? Leave the other places out of `mapping.csv` and the other pack plays there.
The `@StartGame`, `@EndGame` and `@Orb` triggers mix the same way. Note that DWEM re-picks only when the place or the
depth changes and then loops that track; there is no automatic next-track rotation while you stay on one floor.

## Notes

- Music loops until you change place. Tracks with a long intro will repeat the intro; trim them if that bothers you.
- BGM in DWEM is marked experimental. It stops at the lobby, and place-based changes are paused while you hold the Orb
  (the `@Orb` track plays when you pick it up).
- DWEM reads every pack in your rc fully into memory when a game starts (the zip, then each file as an in-memory
  Blob), and decodes the track that is playing on top of that. The UST pack alone is ~112 MB, so a pack of a few dozen
  tracks (roughly 50-100 MB) is in the same range. `--bitrate 96k` and `--format opus` shrink it; `--normalize` evens out
  loudness between tracks.
- A `depth` row is *added* to a whole-branch row for the same place as another random candidate, it does not replace it.
- If your friend wants the same setup he builds his own pack from his own files with the same `mapping.csv`.

## Options

`python3 tools/build_pack.py --help`: `--audio DIR`, `--map FILE`, `--name NAME` (zip name and `local://NAME.zip`),
`--out DIR`, `--format auto|opus|mp3|copy`, `--bitrate 112k`, `--normalize`.

## License

MIT for the tool and mapping, see [LICENSE](LICENSE). The music you load is yours and is not part of this repo.
