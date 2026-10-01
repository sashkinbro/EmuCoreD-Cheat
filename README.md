# EmuCoreD-Cheat

Nintendo 3DS cheat catalog for [EmuCoreD](https://github.com/sashkinbro/EmuCoreD).

The catalog is consumed by the app's cheat manager. Cheat files use the
Azahar/Citra cheat format: a plain text file named after the 16-character
title id, with `[name]` sections and `XXXXXXXX YYYYYYYY` code lines.

## Layout

- `cheats.json` - the catalog consumed by the app
- `files/<source>/<TITLEID>.txt` - redistributable cheat files
- `sources.json` - upstream sources and their licenses
- `schemas/cheat-catalog.schema.json` - catalog schema

## Status

The catalog links 632 community cheat files covering 625 titles from
[CTRPF-AR-CHEAT-CODES](https://github.com/iSharingan/CTRPF-AR-CHEAT-CODES).
The upstream repository has no redistribution license, so files are linked
rather than mirrored. Entries use the Gateway cheat format consumed by Azahar.

No game data is distributed here. Nintendo 3DS is a trademark of Nintendo.
