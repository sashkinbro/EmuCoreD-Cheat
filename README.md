# EmuCoreD-Cheat

Typed cheat catalogs for the nine Nintendo platforms supported by
[EmuCoreD](https://github.com/sashkinbro/EmuCoreD). No ROMs, BIOS files,
Nintendo encryption keys, or save games are distributed here.

## Published catalogs

| Platform | Source files | Cheat blocks | Files with exact source identities | Manual selection only |
| --- | ---: | ---: | ---: | ---: |
| Nintendo 3DS | 632 | 12,327 | 632 | 0 |
| Nintendo DS | 4,082 | 645,072 | 2,004 | 2,078 |
| GameCube | 225 | 4,029 | 225 | 0 |
| Wii | 42 | 134 | 42 | 0 |
| Game Boy Advance | 513 | 7,015 | 174 | 339 |
| Game Boy | 1,484 | 16,849 | 933 | 551 |
| Game Boy Color | 933 | 9,274 | 529 | 404 |
| NES / Famicom | 2,243 | 43,810 | 1,455 | 788 |
| SNES / Super Famicom | 2,762 | 68,809 | 1,556 | 1,206 |
| **Total** | **12,916** | **807,319** | **7,550** | **5,366** |

These are source/catalog validation counts, **not guest execution test results**.
Some source blocks require a format unsupported by a particular emulator adapter.
Every code starts disabled. Much of the DS total consists of per-value item
and character selectors from the upstream database.

- `platforms.json`: schema 2 manifest with nine index locations, hashes and sizes.
- `platforms/<platform>/index.json`: per-platform pack index. IDs are `n3ds`,
  `nds`, `gamecube`, `wii`, `gba`, `gb`, `gbc`, `nes`, `snes`.
- `platforms/<platform>/packs/<id>.json`: typed blocks, identity evidence,
  source revision/digest, original source text and per-source license.
- `cheats.json`: backward-compatible schema 1 **3DS-only** catalog, now with
  immutable source URLs and verified block counts. Existing IDs are unchanged.
- `sources-v2.json`, `LICENSES/`, and `UPSTREAM-CREDITS.cht`: source pins,
  licenses and original contributor acknowledgements.
- `reports/`: validation results and explicitly excluded family files.

## Matching and execution boundaries

No serial, digest, region, revision or code is fabricated. Cartridge mappings
require an **exact DAT name**, including region and revision; only a documented
cheat-device suffix may be removed. Mapped records carry source ROM CRC32,
MD5/SHA1, byte size, region, revision and immutable DAT provenance. Hashes refer
to the exact ROM bytes described by that DAT. They are not DS header CRCs,
archive hashes, RVZ hashes or adjusted headered/headerless variants.

Files without an exact DAT record remain `unmapped-manual-only`. Similar titles,
other regions and other revisions are never silently substituted. A source
name match documents the intended game, not proof that every code works.
Consumers should require an exact platform and ROM digest when available.

Dolphin packs retain real six-character guest IDs. Revisions are recorded only
when specified upstream; otherwise they remain `unspecified-upstream`.
Three-character family INIs are excluded rather than expanded into guessed IDs.

Formats stay separate: DS Action Replay; Dolphin Action Replay/Gecko; GB/GBC
Game Genie/GameShark; GBA CodeBreaker/Action Replay/GameShark; NES/SNES Game
Genie and raw/device codes. `retroarch-memory`, `unclassified`,
`gba-device-unspecified`, and Dolphin `*-unparsed` blocks **must not be passed
to a native parser as a guessed format**. Complete source fields/text are
retained. Malformed Dolphin lines quarantine their entire block; whitespace
and inline credits do not discard valid instructions. No code is auto-enabled.
Encrypted Dolphin Action Replay is explicitly marked `*-encrypted`; mixed
encrypted/hex blocks remain unsupported as `*-mixed-unparsed`. Encrypted AR
lines are never accepted as Gecko, and GBA device formats require valid word
widths and complete pairs even when the source filename names a device.

3DS files stay **link-only** because CTRPF-AR-CHEAT-CODES has no redistribution
license. Their pinned SHA-256 and sizes are recorded; no 3DS code text is
mirrored. CTRPF has extensions beyond basic Gateway codes, so adapters must
reject unsupported commands rather than assume all upstream files work.

## Sources and licensing

- [libretro-database](https://github.com/libretro/libretro-database): Nintendo
  cartridge cheats and exact No-Intro metadata, under its published **CC BY-SA
  4.0** license. Contributor/source credits are preserved. Typed extraction and
  default-disabled changes are identified in every pack.
- [Dolphin](https://github.com/dolphin-emu/dolphin): ActionReplay/Gecko sections
  from pinned `Data/Sys/GameSettings`, under the repository's **GPL-2.0-or-later**
  default. Upstream COPYING and license text are included.
- [CTRPF-AR-CHEAT-CODES](https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES):
  unlicensed community 3DS source, linked only.

Each source's terms remain attached to its data; there is no replacement
blanket license. CC BY-SA 4.0 permits commercial use with its attribution and
share-alike requirements. Creative Commons also
[lists GPLv3 as a compatible adaptation license](https://creativecommons.org/compatible-licenses/).
The new generator, validator and parser tests are MIT licensed separately.
Catalog availability does not mean all runtime/UI adapters implement each format.

## Rebuild and verify

Python 3.10+ and Git suffice. Check out exact source revisions from
`sources-v2.json`. Source bytes are read from Git objects, avoiding Windows
line-ending changes to published digests.

```text
python -m unittest discover -s scripts -p test_multiplatform.py
python scripts/build_multiplatform.py --libretro <checkout> --ctrpf <checkout> --dolphin <checkout> --generated-at <manifest-timestamp>
python scripts/validate_multiplatform.py
python scripts/validate_catalog.py
```

Default source paths are `.upstream-libretro`, `.upstream-ctrpf`, and
`../coreGameCube/dolphin`; source checkouts are excluded from Git. The validator
checks every source/index/payload hash, identity boundary, disabled state,
recognized code-line shape and legacy compatibility. It does not claim
hardware execution.
