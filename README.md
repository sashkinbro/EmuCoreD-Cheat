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

The catalog is being populated. Redistributable files are mirrored in this
repository; entries without redistribution permission link to their authors'
downloads. The catalog credits the original sources.

No game data is distributed here. Nintendo 3DS is a trademark of Nintendo.
