-- Main functionality
function onload(saved)
	restoreSettings(saved)
	buildDataStructure()
	registerObjectGUIDs()
	buildTableButtons()
	addZoneContextMenus()
	for _, guid in pairs({ "cb1610", "a7a029", "4c02f8", "a3e6a8", "9c553c", "eb479b", "3d4319", "540e21" }) do
		pcall(function()
			getObjectFromGUID(guid).interactable = false
		end)
	end
	Wait.frames(function()
		for _, guid in pairs({ "02e062", "de4346", "d936a8", "b93b40" }) do
			pcall(function()
				getObjectFromGUID(guid).interactable = false
			end)
		end
	end, 5)

	-- flip hands on load
	Hands.disable_unused = false
	Wait.condition(function()
		local Zones = Encoder.call("APIlistZones", {})
		for guid, zone in pairs(Zones) do
			local objs = getObjectFromGUID(guid).getObjects()
			for _, obj in pairs(objs) do
				if obj.type == "Card" then
					local rot = obj.getRotation()
					rot[3] = 180
					obj.setRotation(rot)
				end
			end
		end
	end, function()
		return Encoder ~= nil
	end)

	-- 4pl specific vars
	revealNrow = 12
	revealUp = 15.5
	revealUpS = 3.1
	revealRi = 1.5
	exileRot = -180
	gravFor = -4.14

	spawnPatchNotesButton()
	checkForUpdate()
	spawnLandTrackerText()
	spawnKeepButtons()
	initFetchlands()
	initStickerBagMenu()
	-- give objects a moment to finish spawning, then re-hang the Mindmoil buttons
	-- (a loaded save can restore stale ones; refreshMindmoilButtons dedupes)
	Wait.time(refreshMindmoilButtons, 1)
	-- keep our card buttons alive across the Encoder's rebuilds (card_buttons.lua)
	registerGlobalCardButtons()
end

-- Ensure data structure exists. The seats come from the table config (SEAT_COLORS /
-- SEATS), which the build prepends from tables/<table>/ -- see tables/build.py.
function buildDataStructure()
	data = {}
	for _, color in ipairs(SEAT_COLORS) do
		data[color] = { deck = nil }
	end
end

-- per-seat object GUIDs, copied from the table config into data[color]
seatObjectKeys = {
	"libraryZone", -- library scripting zone
	"graveyard",
	"playmat", -- playmat scripting zone
	"landZone", -- dedicated land scripting zone on each playmat (where lands are played)
	"commandZone", -- command-zone scripting zone, used by the reset button to snapshot/restore commanders
	"exileZone", -- exile scripting zone; the reset button clears these too
	"mulliganButton",
	"untapButton",
	"drawButton",
	"scryButton",
	"millButton",
	"revealButton",
	"lifeTracker",
}

-- Get pointers to in-game objects so we can script them
function registerObjectGUIDs()
	for _, color in ipairs(SEAT_COLORS) do
		local seat = SEATS[color]
		for _, key in ipairs(seatObjectKeys) do
			data[color][key] = getObjectFromGUID(seat[key])
		end
		-- Commander-damage trackers grouped by the player who *receives* the damage.
		-- A tracker's Description is its *source* colour (the dealer), not the
		-- recipient -- a player's own board holds one tracker per opponent, so the
		-- config lists that recipient -> trackers mapping.
		data[color]["commanderDamage"] = seat.commanderDamage
	end
end

-- per-colour card spawn points (Scryfall spawner) and library fan direction
props = {}
deckDirs = {}
for _, color in ipairs(SEAT_COLORS) do
	props[color] = { spawns = SEATS[color].spawns }
	deckDirs[color] = SEATS[color].deckDir
end

--------------------------------------------------------------------------------
--------------------------------------------------------------------------------
function onPlayerDisconnect(player) -- flip cards in hand if disconnected
	for handInd = 1, player.getHandCount() do
		objs = player.getHandObjects(handInd)
		for _, obj in pairs(objs) do
			local rot = obj.getRotation()
			rot[3] = 180
			obj.setRotation(rot)
		end
	end
end

