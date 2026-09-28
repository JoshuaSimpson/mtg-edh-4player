# MTG EDH 4-player (χ)

A scripted [Tabletop Simulator](https://store.steampowered.com/app/286160/) mod for 4-player Magic: The Gathering Commander. Fork of [MTG EDH 4-player (π)](https://steamcommunity.com/sharedfiles/filedetails/?id=2296042369).

## Layout

- `src/*.lua` — the Lua source, split into modules.
- `main.lua` — built artifact: the seat config plus `src/` concatenated (don't edit directly).
- `tables/` — per-table seat configs (`4p/seats.json`) and `build.py`, which generates the 6-player table into `build/6p/`.
- `ui.xml` — Global screen-space UI.
- `objects/<name>.<guid>.json` — per-object save data (transforms, image URLs, contained cards, …), one file per table object.
- `objects/<name>.<guid>.{lua,xml}` — that object's script / UI (single source; injected into the JSON at build time).
- `save.template.json` — the save metadata around the objects (grid, lighting, hands, …); the global script comes from `main.lua` / `ui.xml`.
- `Makefile` — rebuilds `main.lua` and assembles full saves.
- `tts_push.py` — live-pushes the script + UI to a running game.
- `tts_save.py` — splits a TTS save into the per-object JSON above and rebuilds it.

## Development

### Saves

The whole table — every card, deck, token, transform and image URL — is tracked
as per-object JSON, not just the scripts. To pull a save apart and put it back:

```sh
make split SAVE="path/to/TS_Save_NN.json"   # save -> objects/*.json + save.template.json
make save                                    # objects/*.json + main.lua/ui.xml -> a fresh save
```

`make split` defaults to the most-recently-modified `TS_Save_*.json`. `make save`
writes `MTG EDH 4-player (χ) <version>-<YYYYMMDDHHMMSS>.json` (version read from
`src/ui/patchnotes.lua`) into the directory named by `SAVE_DIR` in a local `.env`
(copy `.env.example`); override per-run with `make save SAVE_OUT="path/to/Saves"`.

### 6-player table

`make save TABLE=6p` builds a 6-player version of the table (three seats per
long side; Green and Purple join). It is generated from the 4-player table by
`tables/build.py` into `build/6p/` (not committed), so changes to the 4-player
table and scripts carry over automatically. Don't `make split` a 6-player save.

Releases are versioned with git tags (`vX.Y.Z`); bump `VERSION` in `src/ui/patchnotes.lua` when cutting one.
