# SPDX-License-Identifier: MIT
"""Validate every catalog payload, source digest, identity and code boundary."""
import hashlib
import json
import pathlib
import re
import subprocess
from urllib.parse import unquote, urlparse
from build_multiplatform import GitBlobs

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLATFORMS = {'n3ds', 'nds', 'gamecube', 'wii', 'gba', 'gb', 'gbc', 'nes', 'snes'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked_file(entry):
    path = (ROOT / entry['path']).resolve()
    assert path.is_relative_to(ROOT.resolve()), 'Path escapes repository'
    raw = path.read_bytes()
    assert len(raw) == entry['sizeBytes'], str(path) + ': wrong size'
    assert hashlib.sha256(raw).hexdigest() == entry['sha256'], str(path) + ': wrong hash'
    return json.loads(raw)


def validate():
    sources = read(ROOT / 'sources-v2.json')
    blob_sources = {key: GitBlobs(path, sources[key]['revision']) for key, path in
                   [('libretro', ROOT / '.upstream-libretro'), ('ctrpf', ROOT / '.upstream-ctrpf'),
                    ('dolphin', ROOT.parent / 'coreGameCube/dolphin')]}
    manifest = read(ROOT / 'platforms.json')
    assert manifest['schemaVersion'] == 2
    assert manifest['defaultEnabled'] is False
    assert {platform['id'] for platform in manifest['platforms']} == PLATFORMS
    ids, total_blocks, total_files, mapped = set(), 0, 0, 0
    for platform in manifest['platforms']:
        catalog = checked_file(platform)
        assert catalog['platform'] == platform['id']
        entries = catalog['entries']
        assert entries and len(entries) == platform['files']
        assert sum(entry['blockCount'] for entry in entries) == platform['blocks']
        assert sum(bool(entry['identities']) for entry in entries) == platform['mappedFiles']
        assert catalog['stats']['manualOnlyFiles'] == sum(not entry['identities'] for entry in entries)
        for entry in entries:
            assert entry['id'] not in ids, 'Duplicate pack id'
            ids.add(entry['id'])
            assert entry['blockCount'] > 0
            if platform['id'] == 'n3ds':
                assert entry['distribution'] == 'link-only'
                assert sources['ctrpf']['revision'] in entry['downloadUrl']
                assert all(re.fullmatch('[0-9A-F]{16}', identity['titleId']) for identity in entry['identities'])
                assert 'blocks' not in entry and 'originalText' not in entry
                source_path = ROOT / '.upstream-ctrpf' / unquote(urlparse(entry['downloadUrl']).path).split('/' + sources['ctrpf']['revision'] + '/', 1)[1]
                assert source_path.is_file()
                source_rel = source_path.relative_to(ROOT / '.upstream-ctrpf').as_posix()
                assert hashlib.sha256(blob_sources['ctrpf'].read(source_rel)).hexdigest() == entry['sourceSha256']
            else:
                pack = checked_file(entry)
                assert pack['id'] == entry['id'] and pack['platform'] == platform['id']
                assert pack['autoEnable'] is False and pack['guestTested'] is False
                assert pack['identities'] == entry['identities']
                assert len(pack['blocks']) == entry['blockCount']
                assert sorted({block['format'] for block in pack['blocks']}) == entry['formats']
                assert all(block['enabled'] is False and block['guestTested'] is False for block in pack['blocks'])
                source_key = 'dolphin' if platform['id'] in ('gamecube', 'wii') else 'libretro'
                assert pack['sourceRevision'] == sources[source_key]['revision']
                assert pack['sourceRevision'] in pack['sourceUrl']
                source_root = ROOT.parent / 'coreGameCube/dolphin' if source_key == 'dolphin' else ROOT / '.upstream-libretro'
                source_path = source_root / pack['sourcePath']
                assert source_path.is_file()
                source_bytes = blob_sources[source_key].read(pack['sourcePath'])
                assert hashlib.sha256(source_bytes).hexdigest() == pack['sourceSha256']
                assert source_bytes.decode('utf-8-sig', errors='replace') == pack['originalText']
                if not pack['identities']:
                    assert pack['mappingStatus'] == 'unmapped-manual-only'
                for identity in pack['identities']:
                    if source_key == 'libretro':
                        for key, length in [('crc32', 8), ('md5', 32), ('sha1', 40)]:
                            assert re.fullmatch('[0-9A-F]{' + str(length) + '}', identity[key]), (pack['id'], key)
                        assert identity['hashScope'] == 'source-dat-rom-bytes'
                        assert sources['libretro']['revision'] in identity['provenance']['url']
                    else:
                        assert re.fullmatch('[A-Z0-9]{6}', identity['gameId'])
                        assert identity['gameId'] == pathlib.Path(pack['sourcePath']).stem[:6]
                for block in pack['blocks']:
                    if block['format'] in ('nds-action-replay', 'dolphin-gecko'):
                        assert block['lines'] and all(re.fullmatch('[0-9A-Fa-f]{8} [0-9A-Fa-f]{8}', line) for line in block['lines'])
                    if block['format'] == 'retroarch-memory':
                        assert block['sourceFields'].get('handler', '0') != '0'
                    if block['format'] in ('gba-action-replay', 'gba-gameshark'):
                        tokens = re.split(r'[+\s]+', block['originalCode'].upper().strip())
                        assert len(tokens) >= 2 and len(tokens) % 2 == 0
                        assert all(re.fullmatch('[0-9A-F]{8}', token) for token in tokens)
                    if block['format'] == 'dolphin-action-replay-encrypted':
                        assert block['lines'] and all(re.fullmatch('[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}', line.upper()) for line in block['lines'])
            total_files += 1
            total_blocks += entry['blockCount']
            mapped += bool(entry['identities'])
    legacy = read(ROOT / 'cheats.json')
    assert legacy['schemaVersion'] == 1
    assert len(legacy['entries']) == next(p['files'] for p in manifest['platforms'] if p['id'] == 'n3ds')
    return {'passed': True, 'platformCount': len(PLATFORMS), 'fileCount': total_files,
            'blockCount': total_blocks, 'mappedFiles': mapped, 'manualOnlyFiles': total_files-mapped,
            'guestExecutionVerified': False, 'legacy3dsPreserved': True,
            'allSourceHashesVerified': True, 'allPayloadHashesVerified': True}


if __name__ == '__main__':
    result = validate()
    target = ROOT / 'reports/validation.json'
    target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
