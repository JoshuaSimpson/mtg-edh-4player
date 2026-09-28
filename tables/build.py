#!/usr/bin/env python3
"""
Per-table build steps. The Global script (src/) is shared by every table; what
differs between tables is the seat config (which colours sit where, and the
GUIDs of each seat's zones/buttons/trackers) and the physical objects.

    python3 tables/build.py lua tables/4p/seats.json
        Print the seat config as Lua (SEAT_COLORS / SEATS / PATCH_NOTES_POS).
        The Makefile prepends it to src/ to make main.lua.

    python3 tables/build.py generate6p build/6p
        Generate the 6-player table from the 4-player one (objects/*.json,
        save.template.json, tables/4p/seats.json) into build/6p/:
            seats.lua            the 6p seat config (prepend to src/ -> main.lua)
            save.template.json   save metadata with the 6p snap points
            objects/*.json       every table object, laid out for 6 seats
            objects/*.lua        6p-specific copies of object scripts that
                                 hard-code the 4p colour lists
        tts_save.py build --table 6p assembles those into a save.

The 6p table is derived, not hand-built, so anything changed on the 4p table
(decks, tokens, scripts, module objects) carries over on the next build.

Layout: seats sit three per long side. The 4p outer seats keep their colours;
Purple (south middle) is a copy of White's seat and Green (north middle) a copy
of Yellow's -- the north row is the south row rotated 180 degrees, as on the 4p
table, so every copy is a pure translation along x. Each seat is laid out in a
local coordinate u = x * outward-sign, where the deck/command column sits at the
outer (high-u) end and the playmat inside it:

    u:  0.9 ........ playmat ........ 37.9 | 38.5 .. column .. 43.4

To keep the table from getting huge the playmat is narrowed by SHRINK (from its
inner edge), the column keeps its size, and the three seats are packed with GAP
between them. Objects at the table ends (|x| >= END_X: counters, keyword bags,
modules, importers, ...) slide outward to make room and the table model is
stretched to match.
"""

import copy
import glob
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OBJECTS_DIR = os.path.join(ROOT, "objects")
TEMPLATE_PATH = os.path.join(ROOT, "save.template.json")
SEATS_4P = os.path.join(HERE, "4p", "seats.json")

# ------------------------------------------------------------------ 6p layout
SHRINK = 7.0  # how much narrower each playmat is than on the 4p table
GAP = 1.8  # space between neighbouring seats in a row
MAT_INNER, MAT_OUTER = 0.9, 37.9  # u-extent of the 4p playmat
MAT_WIDTH = MAT_OUTER - MAT_INNER
COL_OUTER = 43.4  # u of the outer edge of the deck/command column
END_X = 44.0  # non-seat objects beyond this |x| belong to a table end
# Half-width of the 4p table model (the stretched asset bundle below). Not known
# exactly -- the table-end bags sit at |x| ~ 54 -- so this is an estimate; tweak it
# if the stretched table ends up too short or too long for the end objects.
TABLE_HALF_WIDTH = 57.0
TABLE_MODEL_GUID = "cb1610"
CMDR_EXTRA_STEP = 1.4  # u offset of the second column of commander-damage trackers

COLORS_6P = ["White", "Red", "Yellow", "Blue", "Green", "Purple"]
NEW_SEATS = {"Purple": "White", "Green": "Yellow"}  # new colour -> 4p seat it copies
# TTS player colour tints, for the new commander-damage bag tokens
PLAYER_RGB = {"Green": (0.192, 0.701, 0.168), "Purple": (0.627, 0.125, 0.941)}
# The 4p hand-counter scripts hide themselves from one side of the table by
# listing that side's colours; widen each list to the 6p side.
SIDE_LIST_PATCHES = [
    ("{'White','Red','Grey'}", "{'White','Red','Purple','Grey'}"),
    ("{'Yellow','Blue','Grey'}", "{'Yellow','Blue','Green','Grey'}"),
    ("{'White','Red'}", "{'White','Red','Purple'}"),
    ("{'Yellow','Blue'}", "{'Yellow','Blue','Green'}"),
]

# seat-config keys, and which part of the seat each object belongs to
COLUMN_KEYS = ("libraryZone", "graveyard", "commandZone", "exileZone")
FRONT_KEYS = ("playmat", "landZone", "mulliganButton", "untapButton", "drawButton",
              "scryButton", "millButton", "revealButton")
WIDE_KEYS = ("playmat", "landZone")  # scaled down with the playmat
GUID_KEYS = COLUMN_KEYS + FRONT_KEYS + ("lifeTracker",)
# per-seat objects not in the seat config, found by nickname + Description colour
COLUMN_NICKNAMES = {"Commander Zone", "Timer"}
FRONT_NICKNAMES = {"Hand Counter", "Hand Counter (Self)", "Hand Counter Screen"}
WIDE_NICKNAMES = {"Highlight Mat"}


# ---------------------------------------------------------------------- Lua out
def lua_value(v, indent):
    pad = "\t" * indent
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        v = round(float(v), 3)
        return str(int(v)) if v == int(v) else repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "{ " + ", ".join(lua_value(x, indent) for x in v) + " }"
    if isinstance(v, dict):
        if all(not isinstance(x, (dict, list)) for x in v.values()):
            return "{ " + ", ".join(f"{k} = {lua_value(x, indent)}" for k, x in v.items()) + " }"
        inner = "".join(f"{pad}\t{k} = {lua_value(x, indent + 1)},\n" for k, x in v.items())
        return "{\n" + inner + pad + "}"
    raise TypeError(v)


def render_lua(cfg: dict, source: str) -> str:
    title = f" TABLE CONFIG: {cfg['name']} "
    bar = "-" * ((80 - len(title)) // 2)
    return (
        f"{bar}{title}{bar}\n"
        f"-- GENERATED by tables/build.py from {source} -- edit that, not this.\n"
        "-- Which colours sit at this table and the GUIDs of each seat's objects; read\n"
        "-- by src/core/init.lua (data[color]) and friends.\n"
        f"SEAT_COLORS = {lua_value(cfg['colors'], 0)}\n"
        f"PATCH_NOTES_POS = {lua_value(cfg['patchNotesPos'], 0)}\n"
        f"SEATS = {lua_value({c: cfg['seats'][c] for c in cfg['colors']}, 0)}\n\n"
    )


# -------------------------------------------------------------------- helpers
def children(obj):
    for key in ("ContainedObjects", "ChildObjects"):
        yield from obj.get(key) or []
    yield from (obj.get("States") or {}).values()


def walk(obj):
    yield obj
    for c in children(obj):
        yield from walk(c)


def safe_name(name: str) -> str:
    name = (name or "unnamed").strip() or "unnamed"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


class GuidMaker:
    """Deterministic new GUIDs (stable across rebuilds), never colliding."""

    def __init__(self, taken):
        self.taken = set(taken)

    def make(self, salt: str) -> str:
        n = 0
        while True:
            g = hashlib.sha1(f"6p:{salt}:{n}".encode()).hexdigest()[:6]
            if g not in self.taken:
                self.taken.add(g)
                return g
            n += 1


def sign(x):
    return 1 if x >= 0 else -1


# ------------------------------------------------------------------ generate
def generate6p(out_dir: str) -> None:
    with open(SEATS_4P, encoding="utf-8") as f:
        seats4 = json.load(f)
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = json.load(f)
    objects = {}
    for p in sorted(glob.glob(os.path.join(OBJECTS_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            o = json.load(f)
        objects[o["GUID"]] = o
    guids = GuidMaker(n.get("GUID") for o in objects.values() for n in walk(o))

    # --- geometry
    mat_w = MAT_WIDTH - SHRINK
    col_w = COL_OUTER - MAT_OUTER
    half = (3 * (mat_w + col_w) + 2 * GAP) / 2  # half the length of a row
    outer_shift = half - COL_OUTER  # column shift for the end seats
    # the middle seat's column sits GAP inside the neighbouring end seat's mat
    middle_shift = MAT_INNER + outer_shift + SHRINK - GAP - COL_OUTER
    end_shift = outer_shift
    table_ratio = (TABLE_HALF_WIDTH + end_shift) / TABLE_HALF_WIDTH

    def group_shift(group, col_shift):
        # column keeps its size; the mat (and everything centred on it) loses
        # SHRINK from its inner edge; the life/commander cluster hugs that edge
        return {"column": col_shift, "front": col_shift + SHRINK / 2, "cluster": col_shift + SHRINK}[group]

    def place(obj, outward, col_shift, group, wide=False):
        t = obj["Transform"]
        u = t["posX"] * outward + group_shift(group, col_shift)
        t["posX"] = round(u * outward, 4)
        if wide:
            t["scaleX"] = round(t["scaleX"] * mat_w / MAT_WIDTH, 4)

    # --- which 4p objects belong to which seat, and to which part of it
    members = {c: {} for c in seats4["colors"]}  # colour -> guid -> (group, wide)
    outward = {}
    for c, seat in seats4["seats"].items():
        outward[c] = sign(objects[seat["libraryZone"]]["Transform"]["posX"])
        for key in GUID_KEYS:
            group = "column" if key in COLUMN_KEYS else "cluster" if key == "lifeTracker" else "front"
            members[c][seat[key]] = (group, key in WIDE_KEYS)
        for g in seat["commanderDamage"]:
            members[c][g] = ("cluster", False)
    for g, o in objects.items():
        nick, desc = o.get("Nickname", ""), o.get("Description", "")
        if desc in members and nick in COLUMN_NICKNAMES | FRONT_NICKNAMES | WIDE_NICKNAMES:
            members[desc][g] = ("column" if nick in COLUMN_NICKNAMES else "front", nick in WIDE_NICKNAMES)
        elif o.get("Name") == "HandTrigger" and o.get("FogColor") in members:
            main_hand = o["Transform"]["scaleX"] > 15  # the small one is the side hand
            members[o["FogColor"]][g] = ("front" if main_hand else "column", main_hand)
    seat_of = {g: c for c, m in members.items() for g in m}

    out = {}  # guid -> object, the 6p table
    scripts = {}  # guid -> script for objects whose tracked .lua needs a 6p copy

    # --- the four existing seats: slide outward, narrow the mat
    for c, m in members.items():
        for g, (group, wide) in m.items():
            o = copy.deepcopy(objects[g])
            place(o, outward[c], outer_shift, group, wide)
            out[g] = o

    # --- everything that isn't a seat
    for g, o in objects.items():
        if g in seat_of:
            continue
        o = copy.deepcopy(o)
        t = o["Transform"]
        if g == TABLE_MODEL_GUID:
            t["scaleX"] = round(t["scaleX"] * table_ratio, 4)
        elif o.get("Name") == "Custom_Assetbundle" and t["posY"] < -40 and abs(t["posX"]) > 1:
            t["posX"] = round(t["posX"] * table_ratio, 4)  # scenery sunk with the table model
        elif abs(t["posX"]) >= END_X:
            t["posX"] = round(t["posX"] + sign(t["posX"]) * end_shift, 4)
        out[g] = o

    # --- the new seats: copies of a 4p seat, translated to the middle
    seats6 = {"name": "6-player", "colors": COLORS_6P, "patchNotesPos": seats4["patchNotesPos"], "seats": {}}
    for c in seats4["colors"]:
        seats6["seats"][c] = copy.deepcopy(seats4["seats"][c])
    new_guid = {}  # (new colour, template guid) -> guid
    for new, tmpl in NEW_SEATS.items():
        for g, (group, wide) in members[tmpl].items():
            if g in seats4["seats"][tmpl]["commanderDamage"]:
                continue  # rebuilt below
            o = copy.deepcopy(objects[g])
            for n in walk(o):
                n["GUID"] = guids.make(f"{new}:{n['GUID']}")
            if o.get("Description") == tmpl:
                o["Description"] = new
            if o.get("FogColor") == tmpl:
                o["FogColor"] = new
            place(o, outward[tmpl], middle_shift, group, wide)
            new_guid[(new, g)] = o["GUID"]
            out[o["GUID"]] = o
            src = tracked_script(g)
            if src is not None:
                o["LuaScript"] = patch_sides(src)  # untracked GUID: carried inline
        seat = copy.deepcopy(seats4["seats"][tmpl])
        for key in GUID_KEYS:
            seat[key] = new_guid[(new, seat[key])]
        seat["commanderDamage"] = []
        seats6["seats"][new] = seat
        outward[new] = outward[tmpl]

    # --- spawn points follow their seat's mat
    for c, seat in seats6["seats"].items():
        tmpl = NEW_SEATS.get(c, c)
        shift = middle_shift if c in NEW_SEATS else outer_shift
        for sp in seat["spawns"].values():
            u = sp["posX"] * outward[tmpl] + group_shift("front", shift)
            sp["posX"] = round(u * outward[tmpl], 2)

    # --- commander damage: every player needs a tracker per opponent (5)
    for c in COLORS_6P:
        tmpl = NEW_SEATS.get(c, c)
        shift = middle_shift if c in NEW_SEATS else outer_shift
        base = sorted(seats4["seats"][tmpl]["commanderDamage"],
                      key=lambda g: abs(objects[g]["Transform"]["posZ"]))
        trackers = []
        for g in base:
            if c in NEW_SEATS:
                o = copy.deepcopy(objects[g])
                o["GUID"] = guids.make(f"{c}:cmdr:{g}")
                place(o, outward[tmpl], shift, "cluster")
                out[o["GUID"]] = o
                src = tracked_script(g)
                if src is not None:
                    o["LuaScript"] = src
            else:
                o = out[g]
            trackers.append(o)
        present = {o["Description"] for o in trackers}
        missing = [s for s in COLORS_6P if s != c and s not in present]
        for i, source in enumerate(missing):
            o = copy.deepcopy(trackers[i])
            o["GUID"] = guids.make(f"{c}:cmdr-extra:{source}")
            o["Description"] = source
            t = o["Transform"]
            t["posX"] = round(t["posX"] + outward[tmpl] * CMDR_EXTRA_STEP, 4)
            src = tracked_script(base[0])
            if src is not None:
                o["LuaScript"] = src
            out[o["GUID"]] = o
            trackers.append(o)
        seats6["seats"][c]["commanderDamage"] = [o["GUID"] for o in trackers]

    # --- commander-damage bags for the new colours, at each table end
    for g, o in list(out.items()):
        if o.get("Nickname") != "Blue Commander Damage" or o.get("Name") != "Custom_Model_Infinite_Bag":
            continue
        end = sign(o["Transform"]["posX"])
        rows = {out[b]["Nickname"].split()[0]: out[b]["Transform"]["posZ"] for b in out
                if out[b].get("Name") == "Custom_Model_Infinite_Bag"
                and out[b].get("Nickname", "").endswith("Commander Damage")
                and sign(out[b]["Transform"]["posX"]) == end}
        for new, z_of in (("Green", "White"), ("Purple", "Red")):
            b = copy.deepcopy(o)
            for n in walk(b):
                n["GUID"] = guids.make(f"{new}:bag:{g}:{n['GUID']}")
                n["Nickname"] = n.get("Nickname", "").replace("Blue", new)
                if n is not b and "ColorDiffuse" in n:
                    r, gg, bb = PLAYER_RGB[new]
                    n["ColorDiffuse"].update({"r": r, "g": gg, "b": bb})
            b["Transform"]["posX"] = round(b["Transform"]["posX"] + end * 1.7, 4)
            b["Transform"]["posZ"] = rows[z_of]
            out[b["GUID"]] = b

    # --- 6p copies of tracked scripts that name the 4p sides
    for g in out:
        src = tracked_script(g)
        if src is not None and patch_sides(src) != src:
            scripts[g] = patch_sides(src)

    # --- snap points: move with their seat, copied for the new seats
    snaps = []
    by_quadrant = {(sign(objects[s["libraryZone"]]["Transform"]["posX"]),
                    sign(objects[s["libraryZone"]]["Transform"]["posZ"])): c
                   for c, s in seats4["seats"].items()}
    for sp in template.get("SnapPoints") or []:
        pos = sp["Position"]
        c = by_quadrant[(sign(pos["x"]), sign(pos["z"]))]
        for target in [c] + [n for n, t in NEW_SEATS.items() if t == c]:
            s = copy.deepcopy(sp)
            u = s["Position"]["x"] * outward[c]
            group = "column" if u >= MAT_OUTER else "cluster"
            shift = middle_shift if target in NEW_SEATS else outer_shift
            s["Position"]["x"] = round((u + group_shift(group, shift)) * outward[c], 4)
            snaps.append(s)
    template = copy.deepcopy(template)
    template["SnapPoints"] = snaps

    # --- write
    objects_out = os.path.join(out_dir, "objects")
    shutil.rmtree(objects_out, ignore_errors=True)
    os.makedirs(objects_out)
    for g, o in out.items():
        base = f"{safe_name(o.get('Nickname') or o.get('Name'))}.{g}"
        with open(os.path.join(objects_out, base + ".json"), "w", encoding="utf-8") as f:
            json.dump(o, f, indent=2, ensure_ascii=False)
        if g in scripts:
            with open(os.path.join(objects_out, base + ".lua"), "w", encoding="utf-8") as f:
                f.write(scripts[g])
    with open(os.path.join(out_dir, "save.template.json"), "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "seats.json"), "w", encoding="utf-8") as f:
        json.dump(seats6, f, indent=2)
    with open(os.path.join(out_dir, "seats.lua"), "w", encoding="utf-8") as f:
        f.write(render_lua(seats6, "tables/4p/seats.json via generate6p"))
    print(f"[6p] {len(out)} objects ({len(out) - len(objects)} new), rows {2 * half:.1f} wide, "
          f"ends +{end_shift:.2f}, table x{table_ratio:.3f} -> {out_dir}")


_script_index = None


def tracked_script(guid):
    """The tracked objects/<name>.<guid>.lua for guid, or None."""
    global _script_index
    if _script_index is None:
        _script_index = {os.path.basename(p)[:-4].rpartition(".")[2]: p
                         for p in glob.glob(os.path.join(OBJECTS_DIR, "*.lua"))}
    p = _script_index.get(guid)
    if p is None:
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def patch_sides(src: str) -> str:
    for a, b in SIDE_LIST_PATCHES:
        src = src.replace(a, b)
    return src


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "lua":
        with open(args[1], encoding="utf-8") as f:
            cfg = json.load(f)
        sys.stdout.write(render_lua(cfg, os.path.relpath(args[1], ROOT)))
    elif len(args) == 2 and args[0] == "generate6p":
        os.makedirs(args[1], exist_ok=True)
        generate6p(args[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
