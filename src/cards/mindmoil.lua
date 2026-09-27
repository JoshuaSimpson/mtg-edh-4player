------------------------------------ MINDMOIL -----------------------------------
-- "Mindmoil" (Whenever you cast a spell, put the cards in your hand on the bottom
-- of your library in any order, then draw that many cards) gets a button on the
-- card itself, and only while the card is sitting on a player's playmat -- it is
-- added when the card settles in a playmat zone and removed when it leaves (see
-- the mindmoilEnter / mindmoilLeave hooks in context_menus.lua). onload rescans
-- every mat so a reload doesn't lose (or duplicate) the button.
--
-- Clicking it resolves the trigger for the mat's owner: their whole hand goes to
-- the bottom of their library, left-to-right in hand = bottom-to-top in the
-- library, and they then draw that many cards.
--
-- The mat owner's "mindmoil" setting (default on) controls whether the button is
-- offered at all; toggling it adds/removes the buttons on that player's mat.

MINDMOIL_CARD_NAME = "mindmoil"

-- vertical gap between the hand cards as they are fanned above the library spot,
-- and how far clear of that fan the library itself is hoisted while they drop.
-- Keep the gap small: it only has to order the cards, and a tall fan means a long
-- fall for the library afterwards.
mindmoilCardGap = 0.15
mindmoilDeckLift = 1.5
-- how long to let the cards get moving before watching for them to settle, and how
-- long to wait for each of the two settles (the hand landing, then the library
-- dropping back on top of it) before giving up and carrying on regardless
mindmoilWatchDelay = 0.4
mindmoilSettleTimeout = 3
mindmoilMergeTimeout = 3

-- per-colour re-entry guard, so a double click can't run two triggers at once
mindmoilRunning = mindmoilRunning or {}

-- is this object the Mindmoil card? (nicknames in this mod are
-- "<name>\n<type line> <cmc>CMC", so compare only the displayed name)
function isMindmoilCard(obj)
	if obj == nil or obj.type ~= "Card" then
		return false
	end
	return mainCardName(obj.getName()):lower() == MINDMOIL_CARD_NAME
end

-- the colour of the playmat this card is currently sitting on, or nil
function mindmoilMatColor(card)
	if card == nil then
		return nil
	end
	for _, zone in ipairs(card.getZones()) do
		local color = playmatColorOfZone(zone)
		if color ~= nil then
			return color
		end
	end
	return nil
end

--------------------------------- THE BUTTON ------------------------------------

-- drop any Mindmoil button(s) already on the card (high-to-low so indices hold)
function removeMindmoilButton(card)
	if card == nil then
		return
	end
	local indices = {}
	for _, b in ipairs(card.getButtons() or {}) do
		if b.click_function == "mindmoilTrigger" then
			table.insert(indices, b.index)
		end
	end
	table.sort(indices, function(a, b)
		return a > b
	end)
	for _, idx in ipairs(indices) do
		card.removeButton(idx)
	end
end

-- put the trigger button just below the card face. Clear first so a card that
-- re-enters a mat (or a reload that kept the old button) can't end up with two.
function addMindmoilButton(card)
	if card == nil then
		return
	end
	removeMindmoilButton(card)
	card.createButton({
		click_function = "mindmoilTrigger",
		function_owner = self,
		label = "Mindmoil",
		tooltip = "                [b]Mindmoil[/b]\nput your hand on the bottom of your\n"
			.. "library (left to right = bottom to top),\nthen draw that many cards",
		position = { 0, 0.2, 1.9 },
		rotation = { 0, 0, 0 },
		width = 1400,
		height = 400,
		font_size = 220,
		scale = { 0.6, 0.6, 0.6 },
		color = { 0.16, 0.16, 0.16 },
		font_color = { 1, 1, 1 },
		hover_color = { 0.4, 0.4, 0.4 },
		press_color = { 1, 0, 0, 0.2 },
	})
end

-- zone hooks (called from onObjectEnterZone / onObjectLeaveZone)
function mindmoilEnter(zone, obj)
	local matColor = playmatColorOfZone(zone)
	if not isMindmoilCard(obj) or matColor == nil then
		return
	end
	if not getSetting(matColor, "mindmoil") then
		return
	end
	-- only button it once it has come to rest on the mat, and only if it's still
	-- there (a card merely passing through the zone shouldn't get a button)
	whenSettledInZone(obj, zone, function(o)
		addMindmoilButton(o)
	end)
end

function mindmoilLeave(zone, obj)
	if not isMindmoilCard(obj) or playmatColorOfZone(zone) == nil then
		return
	end
	removeMindmoilButton(obj)
end

-- The Encoder rebuilds a card's entire button set from its own prop data, which
-- drops any button we put there (dropping a keyword token on the card, the untap
-- sweep clearing a stun/exert counter, notepads, token copies, ...). It calls us
-- back at the end of each rebuild so the button goes straight back on -- see
-- card_buttons.lua for the registration. No-ops for anything that isn't a
-- Mindmoil on a mat, since this runs for every rebuild of every encoded object.
function mindmoilReassert(card)
	if not isMindmoilCard(card) then
		return
	end
	local color = mindmoilMatColor(card)
	if color == nil or not getSetting(color, "mindmoil") then
		return
	end
	addMindmoilButton(card)
end

-- rescan a player's mat (or every mat, when color is nil) and make the buttons
-- match the setting: exactly one on each Mindmoil while it's on, none while it's
-- off. Used by onload and by the settings panel, which toggles it live.
function refreshMindmoilButtons(color)
	for c, _ in pairs(data) do
		local mat = data[c] and data[c]["playmat"]
		if mat ~= nil and (color == nil or c == color) then
			local on = getSetting(c, "mindmoil")
			for _, obj in ipairs(mat.getObjects()) do
				if isMindmoilCard(obj) then
					if on then
						addMindmoilButton(obj)
					else
						removeMindmoilButton(obj)
					end
				end
			end
		end
	end
end

--------------------------------- THE TRIGGER -----------------------------------

-- button handler: only the player whose mat the Mindmoil is on may trigger it
function mindmoilTrigger(obj, clickerColor, alt)
	local ownerColor = mindmoilMatColor(obj)
	if ownerColor == nil then
		return
	end
	if not getSetting(ownerColor, "mindmoil") then
		-- setting was switched off with the button still on the card
		removeMindmoilButton(obj)
		return
	end
	if clickerColor ~= ownerColor then
		Player[clickerColor].broadcast(
			"That's " .. ownerColor .. "'s Mindmoil -- only they can trigger it.",
			{ 1, 0.6, 0.2 }
		)
		return
	end
	mindmoilResolve(ownerColor)
end

-- put the whole hand on the bottom of the library, then draw that many cards.
-- The hand moves as one batch: the library is locked and hoisted clear, the cards
-- are fanned in under it with the leftmost lowest, and once they have settled the
-- library is released to drop on top of the pile. Landing order is bottom-up, so
-- left-to-right in hand comes out bottom-to-top in the library.
function mindmoilResolve(color)
	if mindmoilRunning[color] then
		return
	end
	local cards = {}
	for _, obj in ipairs(Player[color].getHandObjects(1)) do
		if obj.type == "Card" then
			table.insert(cards, obj)
		end
	end
	local n = #cards
	if n == 0 then
		broadcastToColor("Mindmoil: your hand is empty.", color, { 0.9, 0.3, 0.3 })
		return
	end
	mindmoilRunning[color] = true
	broadcastToAll(
		color .. "'s Mindmoil: " .. n .. (n == 1 and " card" or " cards") .. " to the bottom, drawing " .. n,
		stringColorToRGB(color)
	)
	mindmoilBuryHand(color, cards)
end

-- slide the whole hand under the player's library in one go (the same trick
-- move2botLib uses, widened to a stack): hoist and lock the library so it can't
-- fall back early, drop the cards into the gap underneath it, then unlock it so it
-- lands on them. Draws the replacements once everything has merged.
function mindmoilBuryHand(color, cards)
	local n = #cards
	local zone = data[color]["libraryZone"]
	local deck = getDeckFromZone(zone)
	if deck == nil then
		deck = getCardFromZone(zone) -- a one-card library isn't a Deck object
	end

	-- the library's spot before we touch it. Dropping it back onto the buried cards
	-- leaves it a little off, and that nudge would accumulate over a game's worth of
	-- Mindmoils, so we put it back exactly where it started once everything merges.
	local pos, homeRot, rotY
	if deck ~= nil then
		pos = deck.getPosition()
		homeRot = deck.getRotation()
		rotY = homeRot.y
		-- hold the library up out of the way: a locked object still answers
		-- setPositionSmooth, it just stops falling until we unlock it again
		deck.setLock(true)
		local up = deck.getPosition()
		up.y = up.y + mindmoilDeckLift + n * mindmoilCardGap
		deck.setPositionSmooth(up, false, true)
	else
		pos = zone.getPosition()
		homeRot = { x = 0, y = zone.getRotation().y, z = 180 }
		rotY = homeRot.y
	end

	-- fan the hand out below the library, leftmost lowest so it lands first
	local guids = {}
	for i, card in ipairs(cards) do
		-- keep the hand zone from pulling the card straight back while it travels
		card.use_hands = false
		local rot = card.getRotation()
		rot.z = 180 -- face down, like the rest of the library
		rot.y = rotY
		card.setRotationSmooth(rot, false, true)
		card.setPositionSmooth({
			x = pos.x,
			y = 1 + (i - 1) * mindmoilCardGap,
			z = pos.z,
		}, false, true)
		table.insert(guids, card.getGUID())
	end

	-- everything is buried and merged: put the library back on its spot and draw
	local function finish()
		for _, guid in ipairs(guids) do
			local loose = getObjectFromGUID(guid)
			if loose ~= nil then
				-- an empty library leaves cards loose on the table: hand them back to
				-- the normal rules so they behave like any other card there
				loose.use_hands = true
			end
		end
		mindmoilRecentreLibrary(color, pos, homeRot)
		mindmoilDraw(color, n)
	end

	-- once every card has landed, let the library go and wait for it to come down
	-- on top of them. The buried cards are destroyed as they merge, so "every guid
	-- gone and the library at rest" is the signal that the drop is complete --
	-- waiting on that rather than a fixed delay is what keeps the deck from being
	-- drawn off (or recentred) while it's still in the air.
	local released = false
	local function release()
		if released then
			return -- condition and timeout can't both fire, but be certain
		end
		released = true
		if deck ~= nil then
			deck.setLock(false)
		end
		local finished = false
		local function once()
			if not finished then
				finished = true
				finish()
			end
		end
		Wait.condition(once, function()
			for _, guid in ipairs(guids) do
				if getObjectFromGUID(guid) ~= nil then
					return false
				end
			end
			local lib = getDeckFromZone(data[color]["libraryZone"])
			return lib ~= nil and lib.resting
		end, mindmoilMergeTimeout, once)
	end
	-- arm the watcher a beat later: straight out of the hand the cards still report
	-- themselves as resting, and we'd release the library before they had moved
	Wait.time(function()
		Wait.condition(release, function()
			for _, guid in ipairs(guids) do
				local card = getObjectFromGUID(guid)
				if card ~= nil and not card.resting then
					return false
				end
			end
			return true
		end, mindmoilSettleTimeout, release)
	end, mindmoilWatchDelay)
end

-- put the library back exactly where it was before the drop, so repeated Mindmoils
-- can't walk it across the mat. Only x/z and the rotation are restored -- the
-- resting height is left to physics, since the deck is taller than it was.
function mindmoilRecentreLibrary(color, home, rot)
	local deck = getDeckFromZone(data[color]["libraryZone"])
	if deck == nil or home == nil then
		return
	end
	deck.setPositionSmooth({ x = home.x, y = deck.getPosition().y, z = home.z }, false, true)
	if rot ~= nil then
		deck.setRotationSmooth(rot, false, true)
	end
end

-- draw the replacement cards once the hand is safely buried
function mindmoilDraw(color, n)
	mindmoilRunning[color] = false
	local deck = getDeckFromZone(data[color]["libraryZone"])
	if deck == nil then
		-- a one-card library isn't a deck: fall back to the single-card draw
		draw1(color)
		announceDrawTriggers(color, 1, false)
		return
	end
	deck.deal(n, color, 1)
	announceDrawTriggers(color, n, false)
end
