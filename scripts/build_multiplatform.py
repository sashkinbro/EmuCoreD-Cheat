# SPDX-License-Identifier: MIT
"""Reproduce typed Nintendo catalogs from pinned public databases, without game data.

No fuzzy title, cross-region, or revision fallback is performed. Unmapped source
files remain available for manual selection; they are never auto-matched by title.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlparse

PLATFORMS = {
    'nds': 'Nintendo - Nintendo DS', 'gba': 'Nintendo - Game Boy Advance',
    'gb': 'Nintendo - Game Boy', 'gbc': 'Nintendo - Game Boy Color',
    'nes': 'Nintendo - Nintendo Entertainment System',
    'snes': 'Nintendo - Super Nintendo Entertainment System',
}
FORMAT_TAG = re.compile(r' \((?:Game ?Genie|Game ?Shark|Action Replay|Code ?Breaker|Pro Action Replay|Xploder)\)$', re.I)
LANGUAGE_TAG = re.compile(r' \((?:En|Fr|De|Es|It|Nl|Pt|Sv|No|Da|Fi|Ja|Zh|Ko|Ru|Pl|Cs|Hu|El|Tr|Ar|He)(?:,(?:En|Fr|De|Es|It|Nl|Pt|Sv|No|Da|Fi|Ja|Zh|Ko|Ru|Pl|Cs|Hu|El|Tr|Ar|He))*\)')
REGION_TAG = re.compile(r'\((?:USA|Europe|Japan|World|Australia|Canada|France|Germany|Spain|Italy|Netherlands|Sweden|Norway|Denmark|Finland|Korea|China|Taiwan|Hong Kong|Brazil|Russia|United Kingdom|Asia)(?:, (?:USA|Europe|Japan|World|Australia|Canada|France|Germany|Spain|Italy|Netherlands|Sweden|Norway|Denmark|Finland|Korea|China|Taiwan|Hong Kong|Brazil|Russia|United Kingdom|Asia))*\)')
PAIR = re.compile(r'^[0-9A-F]{8} [0-9A-F]{8}$')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_head(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


class GitBlobs:
    """Hash pinned Git bytes, never Windows autocrlf-modified working copies."""
    def __init__(self, repository, revision):
        self.revision = revision
        self.process = subprocess.Popen(['git', '-C', str(repository), 'cat-file', '--batch'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, path):
        self.process.stdin.write((self.revision + ':' + path + '\n').encode('utf-8'))
        self.process.stdin.flush()
        header = self.process.stdout.readline().decode('ascii').split()
        if len(header) != 3 or header[1] != 'blob':
            raise ValueError('Missing pinned source: ' + path)
        data = self.process.stdout.read(int(header[2]))
        assert self.process.stdout.read(1) == b'\n'
        return data


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    path.write_bytes(data)
    return {'path': path, 'sha256': sha(data), 'sizeBytes': len(data)}


def clean_title(title):
    previous = None
    while previous != title:
        previous, title = title, FORMAT_TAG.sub('', title)
    return title


def parse_dat(text):
    records = defaultdict(list)
    for match in re.finditer(r'^game \(\s*\n(.*?)^\)', text, re.M | re.S):
        block = match.group(1)
        name = re.search(r'^\s*name "(.*)"\s*$', block, re.M)
        region = re.search(r'^\s*region "(.*)"\s*$', block, re.M)
        if not name:
            continue
        for rom in re.finditer(r'^\s*rom \((.*)\)\s*$', block, re.M):
            fields = dict((m[0], m[1] or m[2]) for m in re.findall(r'(\w+)\s+(?:"([^"]*)"|([^\s)]+))', rom.group(1)))
            if not fields.get('sha1'):
                continue
            identity = {'name': name.group(1), 'region': region.group(1) if region else None,
                        'revision': (re.search(r'\((Rev [^)]+)\)', name.group(1)) or [None, None])[1],
                        'romName': fields.get('name'), 'sizeBytes': int(fields.get('size', 0)),
                        'crc32': fields.get('crc', '').upper(), 'md5': fields.get('md5', '').upper(),
                        'sha1': fields['sha1'].upper(), 'serial': fields.get('serial'),
                        'hashScope': 'source-dat-rom-bytes'}
            records[name.group(1)].append(identity)
    return dict(records)


def title_key(title):
    """Narrow typography aliases; never remove a release qualifier or a word."""
    title = title.replace(' _ ', ' & ').replace('\u2019', "'")
    title = re.sub(r'\s+', ' ', title).strip()
    # No-Intro moves a leading article after the game name. Keep the article.
    parts = title.split(' (', 1)
    base = parts[0]
    article = re.match(r'^(The|A|An) (.+)$', base, re.I)
    if article:
        base = article[2] + ', ' + article[1]
    title = base + (' (' + parts[1] if len(parts) > 1 else '')
    # A multi-region list is a set, but a region subset is never an alias.
    title = REGION_TAG.sub(lambda m: '(' + ', '.join(sorted(m[0][1:-1].split(', '))) + ')', title)
    return title.casefold()


class IdentityMatcher:
    """Only unique, qualified DAT aliases are eligible for automatic lookup.

    A cheat filename without a language tag may refer to one fully qualified
    DAT release, never to multiple language editions. Explicit language tags,
    revisions, beta/hack/enhancement qualifiers and region sets stay intact.
    """
    def __init__(self, records):
        self.records = records
        self.aliases = defaultdict(set)
        for name, identities in records.items():
            # ROM names are aliases only inside these unmodified ROM DATs.
            names = {name} | {pathlib.Path(i['romName']).stem for i in identities if i.get('romName')}
            for alias in names:
                if not REGION_TAG.search(alias):
                    continue
                self.aliases[title_key(alias)].add(name)
                if LANGUAGE_TAG.search(alias):
                    self.aliases[title_key(LANGUAGE_TAG.sub('', alias))].add(name)

    def match(self, title):
        cleaned = clean_title(title)
        if cleaned in self.records:
            names, rule = [cleaned], 'exact-dat-name'
        else:
            names = sorted(self.aliases.get(title_key(cleaned), []))
            if len(names) != 1:
                return []
            rule = 'unique-qualified-dat-alias'
        return [dict(item, mappingEvidence={'sourceTitle': title, 'datName': name, 'rule': rule})
                for name in names for item in self.records[name]]


def match_identity(title, records):
    return IdentityMatcher(records).match(title)


def code_format(platform, code, title, fields):
    if fields.get('handler', '0') != '0':
        return 'retroarch-memory'
    upper = code.upper().strip()
    tokens = re.split(r'[+\s]+', upper)
    if platform == 'nds':
        return 'nds-action-replay' if len(tokens) % 2 == 0 and all(re.fullmatch('[0-9A-F]{8}', t) for t in tokens) else 'unclassified'
    if platform in ('gb', 'gbc'):
        if all(re.fullmatch(r'[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?', t) for t in tokens):
            return 'gb-game-genie'
        if all(re.fullmatch(r'[0-9A-F]{8}', t) for t in tokens):
            return 'gb-gameshark'
    if platform == 'nes':
        if all(re.fullmatch(r'[APZLGITYEOXUKSVN]{6}(?:[APZLGITYEOXUKSVN]{2})?', t) for t in tokens):
            return 'nes-game-genie'
        if all(re.fullmatch(r'[0-9A-F]{4}:[0-9A-F]{2}(?::[0-9A-F]{2})?', t) for t in tokens):
            return 'nes-raw-address-value'
    if platform == 'snes':
        if all(re.fullmatch(r'[0-9A-F]{4}-[0-9A-F]{4}', t) for t in tokens):
            return 'snes-game-genie'
        if all(re.fullmatch(r'[0-9A-F]{8}', t) for t in tokens):
            return 'snes-pro-action-replay'
        if all(re.fullmatch(r'[0-9A-F]{6}:[0-9A-F]{2}', t) for t in tokens):
            return 'snes-raw-address-value'
    if platform == 'gba':
        if len(tokens) % 2 == 0 and all(re.fullmatch('[0-9A-F]{8}', tokens[i]) and re.fullmatch('[0-9A-F]{4}', tokens[i+1]) for i in range(0, len(tokens), 2)):
            return 'gba-codebreaker'
        valid_device_pairs = len(tokens) >= 2 and len(tokens) % 2 == 0 and all(re.fullmatch('[0-9A-F]{8}', token) for token in tokens)
        if valid_device_pairs and 'action replay' in title.lower():
            return 'gba-action-replay'
        if valid_device_pairs and ('gameshark' in title.lower() or 'game shark' in title.lower()):
            return 'gba-gameshark'
        return 'gba-device-unspecified'
    return 'unclassified'


def parse_cht(text, platform, title=''):
    entries = defaultdict(dict)
    for line in text.splitlines():
        match = re.match(r'^\s*cheat(\d+)_(\w+)\s*=\s*(.*?)\s*$', line)
        if match:
            value = match[3]
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            entries[int(match[1])][match[2]] = value
    blocks = []
    for number, fields in sorted(entries.items()):
        code = fields.get('code', '').strip()
        # RetroArch categories contain descriptions only; memory-handler entries
        # carry their complete fields separately and are never passed to a core.
        if not code and fields.get('handler', '0') == '0':
            continue
        fmt = code_format(platform, code, title, fields)
        tokens = re.split(r'[+\s]+', code.upper())
        if fmt == 'nds-action-replay':
            lines = [' '.join(tokens[i:i+2]) for i in range(0, len(tokens), 2)]
        elif fmt == 'gba-codebreaker':
            lines = [' '.join(tokens[i:i+2]) for i in range(0, len(tokens), 2)]
        else:
            lines = [t for t in code.split('+') if t.strip()]
        blocks.append({'id': str(number), 'title': fields.get('desc', f'Cheat {number}'),
                       'format': fmt, 'lines': lines, 'originalCode': code,
                       'enabled': False, 'sourceFields': fields, 'guestTested': False})
    return blocks


def parse_dolphin(text):
    section, current, blocks = '', None, []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith('[') and line.endswith(']'):
            section, current = line[1:-1], None
        elif section in ('ActionReplay', 'Gecko') and line.startswith('$'):
            author = re.search(r' \[([^]]+)\]$', line)
            current = {'id': str(len(blocks)), 'title': line[1:], 'format': 'dolphin-' + ('action-replay' if section == 'ActionReplay' else 'gecko'),
                       'lines': [], 'enabled': False, 'guestTested': False}
            if author:
                current['author'] = author[1]
            blocks.append(current)
        elif current is not None and line and not line.startswith(('#', '*', ';')):
            # Preserve encrypted AR codes as their own type; do not hex-decode.
            pair = re.fullmatch(r'([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})(?:\s+[\[#;].*)?', line)
            if pair:
                current['lines'].append(pair[1].upper() + ' ' + pair[2].upper())
                current['_hex'] = True
            elif section == 'ActionReplay' and re.fullmatch(r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}', line.upper()):
                current['lines'].append(line)
                current['_encrypted'] = True
            else:
                current.setdefault('unparsedLines', []).append(line)
                if not current['format'].endswith('-unparsed'):
                    current['format'] += '-unparsed'
    for block in blocks:
        hex_lines, encrypted_lines = block.pop('_hex', False), block.pop('_encrypted', False)
        if encrypted_lines:
            block['format'] = 'dolphin-action-replay-' + ('mixed-unparsed' if hex_lines else
                              'encrypted-unparsed' if block.get('unparsedLines') else 'encrypted')
    return [block for block in blocks if block['lines'] or block.get('unparsedLines')]


def main():
    parser = argparse.ArgumentParser()
    root = pathlib.Path(__file__).resolve().parents[1]
    parser.add_argument('--libretro', type=pathlib.Path, default=root / '.upstream-libretro')
    parser.add_argument('--ctrpf', type=pathlib.Path, default=root / '.upstream-ctrpf')
    parser.add_argument('--dolphin', type=pathlib.Path, default=root.parent / 'coreGameCube/dolphin')
    parser.add_argument('--generated-at', help='Reuse manifest timestamp for byte-identical regeneration')
    args = parser.parse_args()
    lib_pin, ctr_pin, dolphin_pin = map(git_head, (args.libretro, args.ctrpf, args.dolphin))
    generated = args.generated_at or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    lib_blobs, ctr_blobs, dolphin_blobs = (GitBlobs(path, pin) for path, pin in
        ((args.libretro, lib_pin), (args.ctrpf, ctr_pin), (args.dolphin, dolphin_pin)))
    indexes = defaultdict(list)
    report = {'schemaVersion': 1, 'generatedAt': generated, 'platforms': {}, 'excluded': [], 'identitySources': [], 'guestExecutionVerified': False}
    license_dir = root / 'LICENSES'
    license_dir.mkdir(exist_ok=True)
    (license_dir / 'CC-BY-SA-4.0.txt').write_bytes(lib_blobs.read('LICENSE'))
    (license_dir / 'Dolphin-COPYING.txt').write_bytes(dolphin_blobs.read('COPYING'))
    (license_dir / 'GPL-2.0-or-later.txt').write_bytes(dolphin_blobs.read('LICENSES/GPL-2.0-or-later.txt'))

    def publish(platform, title, source_path, source_url, source_name, license_id, blocks, identities, raw_bytes, **extras):
        if not blocks:
            return
        entry_id = source_name.lower() + '-' + sha(source_path.encode())[:20]
        payload = {'schemaVersion': 2, 'id': entry_id, 'platform': platform, 'title': title,
                   'sourceUrl': source_url, 'sourceName': source_name, 'sourcePath': source_path,
                   'license': license_id, 'sourceSha256': sha(raw_bytes),
                   'authors': [source_name + ' contributors'], 'blocks': blocks, 'identities': identities,
                   'mappingStatus': 'exact-source-identity' if identities else 'unmapped-manual-only',
                   'autoEnable': False, 'guestTested': False, **extras}
        file_path = root / 'platforms' / platform / 'packs' / (entry_id + '.json')
        info = write_json(file_path, payload)
        indexes[platform].append({'id': entry_id, 'title': title, 'path': file_path.relative_to(root).as_posix(),
                                 'sha256': info['sha256'], 'sizeBytes': info['sizeBytes'],
                                 'blockCount': len(blocks), 'formats': sorted({b['format'] for b in blocks}),
                                 'identities': identities, 'mappingStatus': payload['mappingStatus']})

    for platform, directory in PLATFORMS.items():
        dat_paths = ['metadat/no-intro/' + directory + '.dat']
        if platform == 'nes':
            dat_paths.append('dat/' + directory + '.dat')
        records = defaultdict(list)
        for dat_rel in dat_paths:
            dat_bytes = lib_blobs.read(dat_rel)
            dat_source = {'url': f'https://github.com/libretro/libretro-database/blob/{lib_pin}/{quote(dat_rel)}',
                          'sha256': sha(dat_bytes)}
            parsed = parse_dat(dat_bytes.decode('utf-8-sig'))
            report['identitySources'].append({'platform': platform, 'path': dat_rel,
                                             'recordNames': len(parsed), 'license': 'CC-BY-SA-4.0', **dat_source})
            for name, identities in parsed.items():
                records[name].extend(dict(item, provenance=dat_source) for item in identities)
        matcher = IdentityMatcher(records)
        mapping_rules, ambiguous = Counter(), []
        for file in sorted((args.libretro / 'cht' / directory).glob('*.cht')):
            rel = file.relative_to(args.libretro).as_posix()
            raw = lib_blobs.read(rel)
            text = raw.decode('utf-8-sig', errors='replace')
            blocks = parse_cht(text, platform, file.stem)
            if not blocks:
                continue
            identities = matcher.match(file.stem)
            mapping_rules[identities[0]['mappingEvidence']['rule'] if identities else 'manual-only'] += 1
            candidates = sorted(matcher.aliases.get(title_key(clean_title(file.stem)), []))
            if not identities and len(candidates) > 1:
                ambiguous.append({'sourceTitle': file.stem, 'candidateDatNames': candidates})
            publish(platform, file.stem, rel,
                    f'https://github.com/libretro/libretro-database/blob/{lib_pin}/{quote(rel)}',
                    'libretro-database', 'CC-BY-SA-4.0', blocks, identities, raw,
                    sourceRevision=lib_pin, originalText=text, originalFormat='retroarch-cht',
                    attributionUrl='https://github.com/libretro/libretro-database',
                    modificationNotice='Typed blocks extracted; disabled by default. Original source text retained.')
        write_json(root / 'reports' / (platform + '-mapping.json'),
                   {'schemaVersion': 1, 'platform': platform, 'rules': dict(mapping_rules),
                    'ambiguousAliasesRejected': ambiguous, 'fuzzyMatching': False,
                    'explicitReleaseQualifiersPreserved': True})
        credits = args.libretro / 'cht' / directory / '_Credits.cht'
        if credits.exists():
            target = root / 'platforms' / platform / 'UPSTREAM-CREDITS.cht'
            target.write_bytes(lib_blobs.read(credits.relative_to(args.libretro).as_posix()))

    # Dolphin's six-character filename is the real guest ID. Short wildcard
    # files are not assigned to a made-up game or expanded into guessed IDs.
    for file in sorted((args.dolphin / 'Data/Sys/GameSettings').glob('*.ini')):
        rel = file.relative_to(args.dolphin).as_posix()
        raw = dolphin_blobs.read(rel)
        text = raw.decode('utf-8-sig', errors='replace')
        blocks = parse_dolphin(text)
        if not blocks:
            continue
        if not re.fullmatch(r'[A-Z0-9]{6}(?:r\d+)?', file.stem):
            report['excluded'].append({'source': file.name, 'reason': 'family-or-unidentified-game-id', 'blocks': len(blocks)})
            continue
        game_id = file.stem[:6]
        platform = 'gamecube' if game_id[0] in 'GDPU' else 'wii' if game_id[0] in 'RSFHJL MNQWEX'.replace(' ', '') else None
        if platform is None:
            report['excluded'].append({'source': file.name, 'reason': 'unknown-console-id', 'blocks': len(blocks)})
            continue
        revision_match = re.search(r'r(\d+)$', file.stem)
        revision = int(revision_match[1]) if revision_match else None
        title = next((line[1:].strip() for line in text.splitlines() if line.startswith('#')), game_id)
        publish(platform, title, rel, f'https://github.com/dolphin-emu/dolphin/blob/{dolphin_pin}/{rel}',
                'Dolphin', 'GPL-2.0-or-later', blocks,
                [{'gameId': game_id, 'revision': revision, 'regionCode': game_id[3],
                  'revisionScope': 'exact' if revision is not None else 'unspecified-upstream',
                  'hashScope': None}], raw,
                sourceRevision=dolphin_pin, originalText=text, originalFormat='dolphin-game-ini',
                modificationNotice='ActionReplay and Gecko sections extracted. Original source retained; no codes automatically enabled.')

    # Existing unlicensed 3DS files remain links only. Verify their actual pinned
    # bytes and code counts locally, but never mirror their source/code text.
    legacy = json.loads((root / 'cheats.json').read_text(encoding='utf-8-sig'))
    known_paths = {unquote(urlparse(entry['downloadUrl']).path).split('/master/', 1)[-1]
                   .split('/' + ctr_pin + '/', 1)[-1] for entry in legacy['entries']}
    for source in sorted((args.ctrpf / 'Cheats').rglob('*.txt')):
        rel = source.relative_to(args.ctrpf).as_posix()
        if rel in known_paths or not re.fullmatch(r'[0-9A-Fa-f]{16}', source.stem):
            continue
        title = source.parent.name
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        legacy['entries'].append({'id': f'ctrpf-{slug}-{source.stem.lower()}', 'title': title,
                                 'titleIds': [source.stem.upper()], 'authors': ['CTRPF-AR-CHEAT-CODES contributors'],
                                 'description': f'Cheat codes for {title}.', 'sourceName': 'CTRPF-AR-CHEAT-CODES',
                                 'license': 'No license (link-only)',
                                 'downloadUrl': f'https://raw.githubusercontent.com/iSharingan/CTRPF-AR-CHEAT-CODES/{ctr_pin}/{quote(rel)}',
                                 'sourceUrl': f'https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES/blob/{ctr_pin}/{quote(rel)}'})
    valid_legacy = []
    for entry in legacy['entries']:
        old_path = unquote(urlparse(entry['downloadUrl']).path)
        rel = old_path.split('/master/', 1)[-1].split('/' + ctr_pin + '/', 1)[-1]
        file = args.ctrpf / rel
        if not file.exists():
            report['excluded'].append({'source': entry['id'], 'reason': 'missing-pinned-3ds-source'})
            continue
        raw = ctr_blobs.read(rel)
        lines = raw.decode('utf-8-sig', errors='replace').splitlines()
        count = sum(bool(PAIR.fullmatch(line.strip().upper())) for line in lines)
        if not count:
            report['excluded'].append({'source': entry['id'], 'reason': 'no-recognized-3ds-code-lines'})
            continue
        sections = re.split(r'^\[[^\r\n]*\]\s*$', '\n'.join(lines), flags=re.M)
        actual_blocks = sum(any(PAIR.fullmatch(line.strip().upper()) for line in section.splitlines()) for section in sections)
        entry = dict(entry, blockCount=actual_blocks,
                     downloadUrl=f'https://raw.githubusercontent.com/iSharingan/CTRPF-AR-CHEAT-CODES/{ctr_pin}/{quote(rel)}',
                     sourceUrl=f'https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES/blob/{ctr_pin}/{quote(rel)}')
        valid_legacy.append(entry)
        item = dict(entry, platform='n3ds', formats=['3ds-gateway'],
                    sourceRevision=ctr_pin, sourceSha256=sha(raw), sizeBytes=len(raw),
                    downloadUrl=f'https://raw.githubusercontent.com/iSharingan/CTRPF-AR-CHEAT-CODES/{ctr_pin}/{quote(rel)}',
                    sourceUrl=f'https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES/blob/{ctr_pin}/{quote(rel)}',
                    identities=[{'titleId': title_id, 'revisionScope': 'unspecified-upstream'} for title_id in entry['titleIds']],
                    distribution='link-only', mappingStatus='exact-source-identity',
                    guestTested=False, autoEnable=False, codeLineCount=count)
        indexes['n3ds'].append(item)

    legacy['entries'] = sorted(valid_legacy, key=lambda entry: (entry['title'].casefold(), entry['id']))
    legacy['generatedAt'] = generated
    (root / 'cheats.json').write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    manifest = {'schemaVersion': 2, 'generatedAt': generated, 'platforms': [],
                'legacy3dsCatalog': 'cheats.json', 'defaultEnabled': False,
                'matchingPolicy': 'Exact platform and verified ROM hash or source game/title ID; never fuzzy title auto-application.'}
    for platform in ('n3ds', 'nds', 'gamecube', 'wii', 'gba', 'gb', 'gbc', 'nes', 'snes'):
        entries = sorted(indexes[platform], key=lambda entry: (entry['title'].casefold(), entry['id']))
        assert entries, f'No real entries for {platform}'
        stats = {'files': len(entries), 'blocks': sum(e['blockCount'] for e in entries),
                 'mappedFiles': sum(bool(e['identities']) for e in entries),
                 'manualOnlyFiles': sum(not e['identities'] for e in entries),
                 'formats': dict(Counter(fmt for e in entries for fmt in e['formats']))}
        index_path = root / 'platforms' / platform / 'index.json'
        info = write_json(index_path, {'schemaVersion': 2, 'platform': platform, 'generatedAt': generated,
                                       'stats': stats, 'entries': entries})
        manifest['platforms'].append({'id': platform, 'path': index_path.relative_to(root).as_posix(),
                                      'sha256': info['sha256'], 'sizeBytes': info['sizeBytes'], **stats})
        report['platforms'][platform] = stats
    write_json(root / 'platforms.json', manifest)
    write_json(root / 'reports/build.json', report)
    write_json(root / 'sources-v2.json', {'libretro': {'revision': lib_pin, 'url': 'https://github.com/libretro/libretro-database',
                         'license': 'CC-BY-SA-4.0', 'licensePath': 'LICENSES/CC-BY-SA-4.0.txt'},
                        'dolphin': {'revision': dolphin_pin, 'url': 'https://github.com/dolphin-emu/dolphin',
                         'license': 'GPL-2.0-or-later', 'licensePath': 'LICENSES/Dolphin-COPYING.txt'},
                        'ctrpf': {'revision': ctr_pin, 'url': 'https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES',
                         'license': 'Unlicensed (link-only)', 'mirrored': False}})
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
