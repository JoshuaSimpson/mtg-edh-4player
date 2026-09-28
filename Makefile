SRC = \
	src/core/init.lua \
	src/ui/buttons.lua \
	src/ui/keybinds.lua \
	src/zones/movement.lua \
	src/zones/reveal.lua \
	src/zones/mulligan.lua \
	src/core/reset.lua \
	src/core/pregame.lua \
	src/ui/command_buttons.lua \
	src/ui/card_buttons.lua \
	src/cards/etali.lua \
	src/cards/obnix.lua \
	src/cards/mindmoil.lua \
	src/mechanics/coinflip.lua \
	src/mechanics/stickers.lua \
	src/zones/landtracker.lua \
	src/mechanics/restricted_abilities.lua \
	src/zones/fetchland.lua \
	src/mechanics/dfc.lua \
	src/mechanics/keyword_tokens.lua \
	src/zones/untap.lua \
	src/zones/draw.lua \
	src/zones/draw_triggers.lua \
	src/core/helpers.lua \
	src/ui/context_menus.lua \
	src/mechanics/ownership.lua \
	src/mechanics/cascade.lua \
	src/zones/reveal_type.lua \
	src/external/chat.lua \
	src/external/scryfall.lua \
	src/ui/patchnotes.lua \
	src/core/settings.lua \
	src/ui/bugreport.lua \
	src/core/json.lua

# The Global script is the table's seat config (rendered from JSON by
# tables/build.py) followed by the shared src/ modules.
SEATS_4P = tables/4p/seats.json
TABLE_PY = tables/build.py

main.lua: $(SEATS_4P) $(TABLE_PY) $(SRC)
	python3 $(TABLE_PY) lua $(SEATS_4P) > main.lua.tmp
	cat $(SRC) >> main.lua.tmp
	mv main.lua.tmp main.lua

# The 6-player table is generated from the 4-player one (objects, template and
# seat config) into build/6p/ -- see tables/build.py. Nothing in build/ is
# committed.
build/6p/main.lua: $(SEATS_4P) $(TABLE_PY) $(SRC) $(wildcard objects/*) save.template.json
	python3 $(TABLE_PY) generate6p build/6p
	cat build/6p/seats.lua $(SRC) > build/6p/main.lua

# fail if the committed main.lua doesn't match a fresh build from src/ -- catches
# edits made directly to the generated main.lua (which a rebuild would clobber).
# Also regenerates the 6p table so a change that breaks it fails here too.
.PHONY: check
check:
	@python3 $(TABLE_PY) lua $(SEATS_4P) > main.lua.tmp
	@cat $(SRC) >> main.lua.tmp
	@mv main.lua.tmp main.lua
	@git diff --exit-code -- main.lua \
		&& echo "main.lua is in sync with src/" \
		|| { echo "ERROR: main.lua differs from src/ build -- commit the rebuild"; exit 1; }
	@$(MAKE) --no-print-directory -B build/6p/main.lua

# Reassemble save.template.json + objects/*.json + main.lua + ui.xml into a
# full, loadable TTS save named "MTG EDH 4-player (χ) <version>-<timestamp>.json".
# TABLE=6p builds the 6-player table instead ("MTG EDH 6-player (χ) ...").
# By default it writes to SAVE_DIR from .env; override the directory with
# SAVE_OUT, e.g. make save SAVE_OUT="$HOME/.local/share/Tabletop Simulator/Saves"
SAVE_OUT ?=
TABLE ?= 4p
.PHONY: save
save: $(if $(filter 4p,$(TABLE)),main.lua,build/$(TABLE)/main.lua)
	python3 tts_save.py build --table $(TABLE) $(if $(SAVE_OUT),--out-dir "$(SAVE_OUT)")

# Decompose a TTS save back into per-object JSON + save.template.json.
# Defaults to the most-recently-modified TS_Save; override with SAVE=path.
# Only for the 4-player table -- the 6-player one is generated, not split.
.PHONY: split
split:
	python3 tts_save.py split $(SAVE)

.PHONY: clean
clean:
	rm -f main.lua
	rm -rf build
