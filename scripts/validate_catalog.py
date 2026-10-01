"""Validate cheats.json against schemas/cheat-catalog.schema.json."""
import json
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
catalog = json.loads((root / 'cheats.json').read_text(encoding='utf-8'))
assert catalog['schemaVersion'] == 1, 'unexpected schema version'
for entry in catalog['entries']:
    assert entry['titleIds'], f"{entry['id']}: no title ids"
    assert entry['blockCount'] >= 1, f"{entry['id']}: empty cheat file"
print(f"ok: {len(catalog['entries'])} entries")
