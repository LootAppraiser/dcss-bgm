#!/usr/bin/env python3
"""Build a DWEM SoundSupport background-music pack from YOUR local audio files.

    python3 tools/build_pack.py                 # reads mapping.csv + audio/, writes build/dcss-bgm.zip

Nothing in this repo contains audio. Put your own files in ./audio (it is git-ignored), edit mapping.csv,
run this, then register the zip in the game chat with `/SoundSupport register` and add
`sound_pack += local://dcss-bgm.zip` to your rc.
"""
import argparse, csv, os, re, shutil, subprocess, sys, tempfile, zipfile

AUDIO_EXT = ('.mp3', '.ogg', '.opus', '.flac', '.wav', '.m4a', '.aac', '.wma', '.mp2')

# DCSS names a branch two ways depending on where you look ("Lair" / "Lair of Beasts"). DWEM matches on the
# normalised name, so for these we write both. Keys are normalised (lower case, no "the/a/an", no 's).
ALIASES = {
    'lair': ['Lair', 'Lair of Beasts'],
    'slime pits': ['Slime Pits', 'Pits of Slime'],
    'hell': ['Hell', 'Vestibule of Hell'],
    'tomb': ['Tomb', 'Tomb of the Ancients'],
    'temple': ['Temple', 'Ecumenical Temple'],
    'zot': ['Zot', 'Realm of Zot'],
    'forest': ['Forest', 'Enchanted Forest'],
    'dis': ['Dis', 'Iron City of Dis'],
    'wizlab': ['Wizlab', 'Wizard Laboratory'],
    'desolation': ['Desolation', 'Desolation of Salt'],
    'trove': ['Trove', 'Treasure Trove'],
    'crucible': ['Crucible', 'Crucible of Flesh'],
    'gulch': ['Gulch', 'Gutter Gulch'],
}
TRIGGERS = {'startgame': 'StartGame', 'endgame': 'EndGame', 'orb': 'Orb'}


def norm(s):
    s = s.strip().lower().replace('\u2019', "'")
    s = re.sub(r"'s\b", '', s).replace("'", '')
    s = re.sub(r'\s+', ' ', s)
    for p in ('the ', 'an ', 'a '):
        if s.startswith(p):
            s = s[len(p):]
            break
    return s.strip()


def read_mapping(path):
    rows = []
    with open(path, encoding='utf-8', newline='') as f:
        lines = [l for l in f if l.strip() and not l.lstrip().startswith('#')]
    for n, row in enumerate(csv.DictReader(lines), start=2):
        place = (row.get('place') or '').strip()
        file = (row.get('file') or '').strip()
        if not place or not file:
            continue
        try:
            weight = float((row.get('weight') or '1').strip() or 1)
        except ValueError:
            sys.exit(f'{path}: bad weight for "{place}": {row.get("weight")!r}')
        if weight <= 0:
            sys.exit(f'{path}: weight must be > 0 for "{place}"')
        depth = (row.get('depth') or '').strip()
        m = re.fullmatch(r'(\d+)(?:\s*-\s*(\d+))?', depth) if depth else None
        if depth and not m:
            sys.exit(f'{path}: bad depth {depth!r} for "{place}" (use N or A-B)')
        depths = [None] if not depth else list(range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1))
        rows.append({'place': place, 'depths': depths, 'weight': weight, 'file': file})
    return rows


def find_audio(audio_dir, name):
    p = os.path.join(audio_dir, name)
    if os.path.isfile(p):
        return p
    base = os.path.basename(name).lower()
    folder = os.path.dirname(p) or '.'
    if os.path.isdir(folder):
        for fn in sorted(os.listdir(folder)):
            stem, ext = os.path.splitext(fn)
            if stem.lower() == base and ext.lower() in AUDIO_EXT:
                return os.path.join(folder, fn)
    return None


def have_encoder(name):
    try:
        out = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return False
    return re.search(r'\b' + re.escape(name) + r'\b', out) is not None


def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', os.path.splitext(os.path.basename(s))[0].lower()).strip('_') or 'track'


def convert(src, dst_dir, fmt, bitrate, normalize, used):
    ext = os.path.splitext(src)[1].lower()
    base = slug(src)
    n, name = 1, base
    while name in used:
        n += 1
        name = f'{base}_{n}'
    used.add(name)
    if fmt == 'copy' or (fmt == 'auto' and ext == '.mp3' and not normalize):
        out = os.path.join(dst_dir, name + ext)
        shutil.copyfile(src, out)
        return os.path.basename(out)
    codec, container, rate = ('libopus', '.ogg', '48000') if fmt in ('auto', 'opus') else ('libmp3lame', '.mp3', '44100')
    if not have_encoder(codec):
        sys.exit(f'ffmpeg has no {codec} encoder; try --format copy (keep the files as they are)')
    out = os.path.join(dst_dir, name + container)
    cmd = ['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-i', src, '-vn', '-map_metadata', '-1',
           '-ac', '2', '-ar', rate]
    if normalize:
        cmd += ['-af', 'loudnorm=I=-18:TP=-1.5:LRA=11']
    cmd += ['-c:a', codec, '-b:a', bitrate, out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f'ffmpeg failed on {src}:\n{r.stderr}')
    return os.path.basename(out)


# --- the same rules DWEM's SoundSupport uses to read these lines, to catch mistakes before the game does ---
def paren_args(line):
    a, b = line.find('('), line.rfind(')')
    if a < 0 or b <= a:
        return None
    parts, cur, quote, esc = [], '', None, False
    for ch in line[a + 1:b]:
        if esc:
            cur += ch; esc = False; continue
        if ch == '\\':
            cur += ch; esc = True; continue
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in '"\'':
            quote = ch; cur += ch; continue
        if ch == ',':
            parts.append(cur); cur = ''; continue
        cur += ch
    parts.append(cur)
    return parts


def check_init(init_text, zip_names):
    problems, n = [], 0
    for line in init_text.splitlines():
        t = line.strip()
        if not t or t.startswith('#'):
            continue
        parts = paren_args(t)
        if not parts or len(parts) < 3:
            problems.append(f'unparseable: {t}'); continue
        try:
            w = float(parts[1])
            assert w >= 0
        except Exception:
            problems.append(f'bad weight: {t}'); continue
        path = ','.join(parts[2:]).strip().strip('"\'')
        if path not in zip_names:
            problems.append(f'missing in zip: {path}')
        n += 1
    return n, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    ap.add_argument('--audio', default=os.path.join(root, 'audio'), help='folder with your audio files')
    ap.add_argument('--map', default=os.path.join(root, 'mapping.csv'))
    ap.add_argument('--name', default='dcss-bgm', help='pack name; the zip is <name>.zip, register it, use local://<name>.zip')
    ap.add_argument('--out', default=os.path.join(root, 'build'))
    ap.add_argument('--format', choices=['auto', 'opus', 'mp3', 'copy'], default='auto',
                    help='auto: keep .mp3 as is, convert everything else to Ogg Opus')
    ap.add_argument('--bitrate', default='112k', help='for converted files')
    ap.add_argument('--normalize', action='store_true', help='even out loudness across tracks (re-encodes everything)')
    a = ap.parse_args()

    rows = read_mapping(a.map)
    if not rows:
        sys.exit(f'{a.map} has no rows')
    os.makedirs(a.out, exist_ok=True)
    found, missing = {}, []
    for r in rows:
        src = find_audio(a.audio, r['file'])
        if src is None:
            missing.append(r['file'])
        else:
            found[r['file']] = src
    if missing:
        print('skipped (no file in %s):' % a.audio)
        for m in sorted(set(missing)):
            print('  -', m)
    if not found:
        sys.exit('no audio found; put your files in %s and check mapping.csv' % a.audio)

    tmp = tempfile.mkdtemp(prefix='bgm_')
    try:
        bgm_dir = os.path.join(tmp, 'bgm')
        os.makedirs(bgm_dir)
        used, outfile = set(), {}
        for key, src in found.items():
            if src not in outfile:
                outfile[src] = 'bgm/' + convert(src, bgm_dir, a.format, a.bitrate, a.normalize, used)
        lines = ['# Generated by tools/build_pack.py from mapping.csv. Do not edit by hand.',
                 '# dwem_bgm += (Place[:Depth], weight, "path")   dwem_bgm_trigger += (StartGame|EndGame|Orb, weight, "path")']
        for r in rows:
            if r['file'] not in found:
                continue
            path = outfile[found[r['file']]]
            key = r['place'].lstrip('@')
            if r['place'].startswith('@'):
                trig = TRIGGERS.get(key.lower())
                if not trig:
                    sys.exit(f'unknown trigger {r["place"]!r} (use @StartGame, @EndGame or @Orb)')
                lines.append(f'dwem_bgm_trigger += ({trig}, {r["weight"]:g}, "{path}")')
                continue
            for name in ALIASES.get(norm(r['place']), [r['place']]):
                for d in r['depths']:
                    token = name if d is None else f'{name}:{d}'
                    lines.append(f'dwem_bgm += ({token}, {r["weight"]:g}, "{path}")')
        init_text = '\n'.join(lines) + '\n'
        with open(os.path.join(tmp, 'init.txt'), 'w', encoding='utf-8') as f:
            f.write(init_text)

        zpath = os.path.join(a.out, a.name + '.zip')
        with zipfile.ZipFile(zpath, 'w') as z:
            z.write(os.path.join(tmp, 'init.txt'), 'init.txt', compress_type=zipfile.ZIP_DEFLATED)
            for fn in sorted(os.listdir(bgm_dir)):
                z.write(os.path.join(bgm_dir, fn), 'bgm/' + fn, compress_type=zipfile.ZIP_STORED)
        with zipfile.ZipFile(zpath) as z:
            names = set(z.namelist())
        n, problems = check_init(init_text, names)
        size = os.path.getsize(zpath) / 1e6
        print(f'\nwrote {zpath}: {len(outfile)} tracks, {n} mapping lines, {size:.1f} MB')
        if size > 150:
            print('  note: big pack. It is held in memory while you play; trim tracks or lower --bitrate if the game gets heavy.')
        if problems:
            print('PROBLEMS:'); [print('  -', p) for p in problems]; sys.exit(1)
        print('\nnext: in the game chat run  /SoundSupport register  and pick this zip,')
        print(f'then add to your rc:  sound_pack += local://{a.name}.zip')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
