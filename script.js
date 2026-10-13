"use strict";

/* ============================================================================
   HOW THIS SCRIPT IS ORGANISED

   Read it from top to bottom. Each section only uses things from the sections
   above it.

     1. Game data         Fixed facts: the skills, the XP table, the worlds.
     2. Saved state       The "state" object, and saving it to the browser.
     3. Calculations      Totals, combat level, level caps, the cheapest route.
     4. Hiscores import   Turning pasted hiscores text into levels.
     5. Drawing the page  Functions that show the state on screen.
     6. Reacting to the user   What happens when something is clicked or typed.
     7. Start             Sets everything up when the page loads.

   The basic loop:  the user does something  ->  the state changes  ->
   the state is saved  ->  the whole page is redrawn from the state.

   The editable route preference ratings are not in this file. They are in
   route-preferences.js, which is loaded first.
   ============================================================================ */


/* ============================================================================
   1. GAME DATA
   ============================================================================ */

const MAX_LEVEL = 99;

// The total level worlds that members can join (from the OSRS Wiki).
const WORLD_THRESHOLDS = [500, 750, 1250, 1500, 1750, 2000, 2200, 2350];

// All skills, in the same order the official hiscores list them. The plain
// text import (section 4) depends on this order.
const SKILL_NAMES = [
  "Attack", "Defence", "Strength", "Hitpoints", "Ranged", "Prayer", "Magic",
  "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking", "Crafting",
  "Smithing", "Mining", "Herblore", "Agility", "Thieving", "Slayer", "Farming",
  "Runecraft", "Hunter", "Construction", "Sailing",
];

// Turn each name into a small object, for example:
//   { key: "attack", name: "Attack", minLevel: 1 }
// "key" is the lowercase name. It is used to look skills up and appears in
// the page's HTML. Hitpoints is the only skill that starts at level 10.
const SKILLS = [];
for (const name of SKILL_NAMES) {
  SKILLS.push({
    key: name.toLowerCase(),
    name: name,
    minLevel: name === "Hitpoints" ? 10 : 1,
  });
}

// A lookup table, so SKILL_BY_KEY["attack"] gives the Attack object.
const SKILL_BY_KEY = {};
for (const skill of SKILLS) {
  SKILL_BY_KEY[skill.key] = skill;
}

// Gives the display name for a skill key: skillName("hitpoints") is "Hitpoints".
function skillName(skillKey) {
  return SKILL_BY_KEY[skillKey].name;
}

// True if the value is the key of a real skill. Used to check saved data.
function isSkillKey(value) {
  for (const skill of SKILLS) {
    if (skill.key === value) {
      return true;
    }
  }
  return false;
}

// The skills that count as combat skills.
const COMBAT_SKILLS = ["attack", "defence", "strength", "hitpoints", "ranged", "prayer", "magic"];

// These level caps always appear in the build rules, in this order, and
// cannot be removed.
const DEFAULT_RULE_SKILLS = [
  "attack", "strength", "defence", "hitpoints", "ranged", "magic", "prayer",
];

// Finds a route preference by its id. Returns null if there is no such preference.
// The preferences themselves (ROUTE_PREFERENCES) are defined in route-preferences.js,
// which index.html loads before this file.
function findRoutePreference(id) {
  for (const preference of ROUTE_PREFERENCES) {
    if (preference.id === id) {
      return preference;
    }
  }
  return null;
}

// Builds the experience table from the formula on the OSRS Wiki ("Experience").
// After it runs, XP_FOR_LEVEL[50] is the total XP needed to reach level 50.
function buildXpTable() {
  const table = [0, 0];   // level 1 needs 0 XP (index 0 is unused)
  let points = 0;
  for (let level = 1; level < MAX_LEVEL; level++) {
    points += Math.floor(level + 300 * Math.pow(2, level / 7));
    table[level + 1] = Math.floor(points / 4);
  }
  return table;
}

const XP_FOR_LEVEL = buildXpTable();

// The level a given amount of XP is worth. levelForXp(83) is 2.
function levelForXp(xp) {
  let level = 1;
  while (level < MAX_LEVEL && XP_FOR_LEVEL[level + 1] <= xp) {
    level++;
  }
  return level;
}

// Forces a level into the allowed range for a skill (for example, Hitpoints
// can never be below 10). Anything that is not a number becomes the minimum.
function clampLevel(level, skillKey) {
  const minLevel = SKILL_BY_KEY[skillKey].minLevel;
  if (!Number.isFinite(level)) {
    return minLevel;
  }
  return Math.max(minLevel, Math.min(MAX_LEVEL, Math.round(level)));
}

// The same idea for the number in a level cap rule, which can be 1 to 99.
function clampRuleMax(value) {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.max(1, Math.min(MAX_LEVEL, Math.round(value)));
}


/* ============================================================================
   2. SAVED STATE
   ============================================================================ */

/*
  The "state" object holds everything the user has entered. It is the single
  source of truth: the page is always drawn from it, and it is what gets saved
  in the browser. Here is an example, shortened:

  {
    current:   { attack: { level: 60, xp: 273742 }, ... },  // from the hiscores, or typed in
    target:    { attack: 75, ... },                          // the levels the user is aiming for
    locked:    { attack: true, ... },                        // locked skills are kept as set
    username:  "Some Name",
    hiscoreMode: "hiscore_oldschool",
    rules:     [ { skill: "attack", max: 75, enabled: true, removable: false }, ... ],
    untrimmed: { skill: "slayer", enabled: false },
    routePreferences: { activity: "afk", resources: null }   // one choice per group, or null
  }
*/

// The name the data is saved under in the browser. If the layout of the saved
// data ever changes in a way that old saves cannot be read, change the number
// on the end (v1 to v2). The browser then starts fresh instead of misreading
// the old data.
const STORAGE_KEY = "osrs-level-planner-v1";

// One of the built-in level cap rules, switched off, at the skill's minimum.
function defaultRule(skillKey) {
  return {
    skill: skillKey,
    max: SKILL_BY_KEY[skillKey].minLevel,
    enabled: false,
    removable: false,
  };
}

// The state for a brand new visitor: every skill at its minimum level.
function defaultState() {
  const state = {
    current: {},
    target: {},
    locked: {},
    username: "",
    hiscoreMode: "hiscore_oldschool",
    rules: [],
    untrimmed: { skill: "slayer", enabled: false },
    routePreferences: {},
  };

  for (const skill of SKILLS) {
    state.current[skill.key] = { level: skill.minLevel, xp: XP_FOR_LEVEL[skill.minLevel] };
    state.target[skill.key] = skill.minLevel;
    state.locked[skill.key] = false;
  }
  for (const skillKey of DEFAULT_RULE_SKILLS) {
    state.rules.push(defaultRule(skillKey));
  }
  for (const group of PREFERENCE_GROUPS) {
    state.routePreferences[group.id] = null;
  }
  return state;
}

// Finds a rule for the given skill in a list of rules. Returns -1 if there is none.
function findRuleIndex(rules, skillKey) {
  for (let index = 0; index < rules.length; index++) {
    if (rules[index].skill === skillKey) {
      return index;
    }
  }
  return -1;
}

// Builds the final list of rules from the saved ones. The built-in rules
// always come first, in a fixed order, using the saved version when there is
// one. Any other saved rules were added by the user, so they can be removed.
function mergeWithDefaultRules(savedRules) {
  const leftovers = savedRules.slice();   // a copy, so we can take items out of it
  const merged = [];

  for (const skillKey of DEFAULT_RULE_SKILLS) {
    const index = findRuleIndex(leftovers, skillKey);
    if (index === -1) {
      merged.push(defaultRule(skillKey));
    } else {
      const rule = leftovers.splice(index, 1)[0];
      merged.push({ skill: rule.skill, max: rule.max, enabled: rule.enabled, removable: false });
    }
  }

  for (const rule of leftovers) {
    merged.push({ skill: rule.skill, max: rule.max, enabled: rule.enabled, removable: true });
  }
  return merged;
}

// Reads the saved text from the browser and turns it back into an object.
// Returns null if nothing is saved, or if the saved text is damaged.
function readSavedData() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

// Loads each skill's current level and XP, target and lock from the saved data.
// ("state" in the functions below is the new object being built, not the global one.)
function loadSkills(state, saved) {
  for (const skill of SKILLS) {
    const key = skill.key;

    // Current level and XP.
    const savedCurrent = saved.current ? saved.current[key] : undefined;
    if (savedCurrent) {
      const level = clampLevel(Number(savedCurrent.level), key);
      const xp = Number(savedCurrent.xp);
      state.current[key] = { level: level, xp: xp >= 0 ? xp : XP_FOR_LEVEL[level] };
    }

    // Target level. If it is missing or damaged, aim for the current level.
    const savedTarget = saved.target ? Number(saved.target[key]) : NaN;
    if (Number.isFinite(savedTarget)) {
      state.target[key] = clampLevel(savedTarget, key);
    } else {
      state.target[key] = state.current[key].level;
    }

    state.locked[key] = Boolean(saved.locked && saved.locked[key]);
  }
}

// Loads the build rules: the built-in level caps, and any the user added.
function loadRules(state, saved) {
  if (!Array.isArray(saved.rules)) {
    return;
  }
  const savedRules = [];
  for (const rule of saved.rules) {
    if (rule && isSkillKey(rule.skill)) {
      savedRules.push({
        skill: rule.skill,
        max: clampRuleMax(Number(rule.max)),
        enabled: Boolean(rule.enabled),
      });
    }
  }
  state.rules = mergeWithDefaultRules(savedRules);
}

// Loads the "untrimmed cape" rule.
function loadUntrimmed(state, saved) {
  if (saved.untrimmed && isSkillKey(saved.untrimmed.skill)) {
    state.untrimmed = {
      skill: saved.untrimmed.skill,
      enabled: Boolean(saved.untrimmed.enabled),
    };
  }
}

// Loads the ticked route preferences. A saved preference only counts if this version
// still knows about it, and if it is saved under the group it belongs to.
function loadRoutePreferences(state, saved) {
  if (saved.routePreferences && typeof saved.routePreferences === "object") {
    for (const group of PREFERENCE_GROUPS) {
      const preference = findRoutePreference(saved.routePreferences[group.id]);
      if (preference && preference.group === group.id) {
        state.routePreferences[group.id] = preference.id;
      }
    }
  }

  // Earlier versions saved a single preference as text. Put it in the group it belongs to.
  const earlierPreference = findRoutePreference(saved.routePreference);
  if (earlierPreference) {
    state.routePreferences[earlierPreference.group] = earlierPreference.id;
  }
}

// Builds the state from saved data, falling back to the defaults for
// anything that is missing or does not make sense.
function loadState() {
  const state = defaultState();
  const saved = readSavedData();
  if (!saved) {
    return state;
  }

  loadSkills(state, saved);
  if (typeof saved.username === "string") {
    state.username = saved.username;
  }
  if (typeof saved.hiscoreMode === "string") {
    state.hiscoreMode = saved.hiscoreMode;
  }
  loadRules(state, saved);
  loadUntrimmed(state, saved);
  loadRoutePreferences(state, saved);
  return state;
}

// Saves the state in the browser. This can fail (for example in some private
// browsing modes), and the page still works without saving, so errors are ignored.
function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Nothing to do: the tool simply will not remember anything next time.
  }
}

// The one and only state object. Everything below reads from and writes to it.
const state = loadState();


/* ============================================================================
   3. CALCULATIONS
   These functions only read the state. They never change it, and they never
   touch the page.
   ============================================================================ */

// An object of every skill's current level, for example { attack: 60, defence: 1, ... }.
function currentLevels() {
  const levels = {};
  for (const skill of SKILLS) {
    levels[skill.key] = state.current[skill.key].level;
  }
  return levels;
}

// The same, for the target levels. state.target already has that shape.
function targetLevels() {
  return state.target;
}

// Adds up a set of levels (an object like the ones above) into a total level.
function totalLevel(levels) {
  let total = 0;
  for (const skill of SKILLS) {
    total += levels[skill.key];
  }
  return total;
}

// Works out a combat level from a set of levels, using the formula from the
// OSRS Wiki ("Combat level"). Only the best of melee, ranged and magic counts.
function combatLevel(levels) {
  const base = 0.25 * (levels.defence + levels.hitpoints + Math.floor(levels.prayer / 2));
  const melee = 0.325 * (levels.attack + levels.strength);
  const ranged = 0.325 * Math.floor(levels.ranged * 1.5);
  const magic = 0.325 * Math.floor(levels.magic * 1.5);
  return Math.floor(base + Math.max(melee, ranged, magic));
}

// How much more XP a skill needs to get from its current XP to its target level.
function xpNeededForTarget(skillKey) {
  const current = state.current[skillKey];
  const target = state.target[skillKey];
  if (target <= current.level) {
    return 0;
  }
  return Math.max(0, XP_FOR_LEVEL[target] - current.xp);
}

// The highest level the build rules allow for a skill: the lowest of all the
// checked rules for that skill, or 99 if there are none.
function capFromRules(skillKey) {
  let cap = MAX_LEVEL;
  for (const rule of state.rules) {
    if (rule.enabled && rule.skill === skillKey) {
      cap = Math.min(cap, rule.max);
    }
  }
  return Math.max(cap, SKILL_BY_KEY[skillKey].minLevel);
}

// The same as above, but when the "untrimmed cape" rule is on, every skill
// except the cape skill is also held to a maximum of 98.
function capIncludingUntrimmed(skillKey) {
  const cap = capFromRules(skillKey);
  const untrimmed = state.untrimmed;
  if (untrimmed.enabled && skillKey !== untrimmed.skill) {
    return Math.min(cap, MAX_LEVEL - 1);
  }
  return cap;
}

// The highest total level possible while following every checked rule.
function maxTotalUnderRules() {
  const caps = {};
  for (const skill of SKILLS) {
    caps[skill.key] = capIncludingUntrimmed(skill.key);
  }
  return totalLevel(caps);
}

// The rating a skill has at a given level. A rating is either a plain number
// (the same at every level) or bands such as { 1: 0, 77: 2 }, which means
// "0 from level 1, then 2 from level 77". Anything missing counts as 0.
function ratingAtLevel(rating, level) {
  if (rating === undefined) {
    return 0;
  }
  if (typeof rating === "number") {
    return rating;
  }

  let result = 0;
  let latestStart = 0;
  for (const startText of Object.keys(rating)) {
    // Object keys are always text, so "77" has to be turned back into the number 77.
    const start = Number(startText);
    // Use the band that starts closest to the level without going past it.
    if (start <= level && start >= latestStart) {
      latestStart = start;
      result = rating[startText];
    }
  }
  return result;
}

// The highest rating a route preference can give a skill.
const MAX_RATING = 3;

// The route preferences that are ticked: none, one, or one from each group.
function chosenPreferences() {
  const chosen = [];
  for (const group of PREFERENCE_GROUPS) {
    const preference = findRoutePreference(state.routePreferences[group.id]);
    if (preference) {
      chosen.push(preference);
    }
  }
  return chosen;
}

// Describes the ticked preferences for the header and the route message, for example
// "favouring AFK skills and skills you can buy". Empty if none are ticked.
function chosenPreferenceSummary() {
  const summaries = [];
  for (const preference of chosenPreferences()) {
    summaries.push(preference.summary);
  }
  return summaries.length > 0 ? "favouring " + summaries.join(" and ") : "";
}

// How much a skill's XP cost counts for when a route decides what to train
// next. 1 means no change. With route preferences ticked, skills that the
// preferences rate highly get a smaller number, so they look cheaper and are
// chosen sooner. When two preferences are ticked, a skill counts for as much as the
// weaker of its two ratings, so it is only favoured if both preferences favour it
// ("AFK skills that need no supplies" means skills that are both). This also means
// ticking two never tilts harder than ticking one.
function routeCostFactor(skillKey, level) {
  const chosen = chosenPreferences();
  if (chosen.length === 0) {
    return 1;
  }
  let weakestRating = MAX_RATING;
  for (const preference of chosen) {
    const rating = ratingAtLevel(preference.ratings[skillKey], level);
    weakestRating = Math.min(weakestRating, rating);
  }
  return Math.pow(COST_FACTOR_PER_RATING_POINT, weakestRating);
}

// Works out targets that reach a goal total level using as little XP as
// possible. It starts from your current levels (or your own targets for locked
// skills), then keeps adding one level to whichever skill has the cheapest next
// level, until the goal is reached or every skill is at its cap.
// With a route preference ticked, each skill's cost is adjusted first (see
// routeCostFactor), so the route favours those skills and needs more XP overall.
// Returns the levels it chose and the total it reached.
function cheapestRoute(goalTotal) {
  const levels = {};
  for (const skill of SKILLS) {
    const key = skill.key;
    levels[key] = state.locked[key] ? state.target[key] : state.current[key].level;
  }
  let total = totalLevel(levels);

  while (total < goalTotal) {
    let cheapestSkill = null;
    let cheapestCost = Infinity;

    for (const skill of SKILLS) {
      const key = skill.key;
      const isLocked = state.locked[key];
      const isAtCap = levels[key] >= capIncludingUntrimmed(key);
      if (isLocked || isAtCap) {
        continue;
      }

      // A skill still at its current level may already be part-way to the
      // next one, so use its real XP. Otherwise use the exact XP of its level.
      const stillAtCurrent = levels[key] === state.current[key].level;
      const xpNow = stillAtCurrent ? state.current[key].xp : XP_FOR_LEVEL[levels[key]];
      const xpCost = XP_FOR_LEVEL[levels[key] + 1] - xpNow;
      // The rating that applies is the one for the level the skill is at now.
      const cost = xpCost * routeCostFactor(key, levels[key]);

      if (cost < cheapestCost) {
        cheapestCost = cost;
        cheapestSkill = key;
      }
    }

    if (cheapestSkill === null) {
      break;   // every skill is locked or capped, so the goal cannot be reached
    }
    levels[cheapestSkill] += 1;
    total += 1;
  }

  return { levels: levels, total: total };
}


/* ============================================================================
   4. HISCORES IMPORT
   ============================================================================ */

// True if the text is a whole number such as "42" or "-1".
function isWholeNumber(text) {
  return /^-?\d+$/.test(text);
}

// Reads the JSON version of the hiscores. Returns an object like
// { attack: { level: 60, xp: 273742 }, ... }, or null if the text is not
// hiscores JSON.
function parseJsonHiscores(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    return null;   // not JSON at all
  }
  if (!data || !Array.isArray(data.skills)) {
    return null;
  }

  const stats = {};
  for (const entry of data.skills) {
    if (entry) {
      stats[String(entry.name).toLowerCase()] = { level: entry.level, xp: entry.xp };
    }
  }

  // The hiscores may spell a skill differently from this tool (for example "Runecrafting"
  // instead of "Runecraft"). For any skill not found by name, use its position instead.
  // Like the plain text version, the list starts with Overall, then Attack, and so on.
  // This is only safe when the list has exactly Overall plus one entry per skill. If an
  // entry is missing, everything after it shifts up and positions would give wrong data.
  const first = data.skills[0];
  const hasExpectedLength = data.skills.length === SKILLS.length + 1;
  if (hasExpectedLength && first && String(first.name).toLowerCase() === "overall") {
    for (let index = 0; index < SKILLS.length; index++) {
      const entry = data.skills[index + 1];
      if (entry && !stats[SKILLS[index].key]) {
        stats[SKILLS[index].key] = { level: entry.level, xp: entry.xp };
      }
    }
  }
  return stats;
}

// Reads the older plain text version of the hiscores. Every skill is one
// line of three numbers, "rank,level,xp", starting with Overall. Other
// lines (such as minigame scores) are ignored.
function parseTextHiscores(text) {
  const skillLines = [];
  for (const line of text.split(/\r?\n/)) {
    const parts = line.trim().split(",");
    if (parts.length === 3 && parts.every(isWholeNumber)) {
      skillLines.push(parts);
    }
  }

  // skillLines[0] is Overall, so Attack is skillLines[1], and so on.
  const stats = {};
  for (let index = 0; index < SKILLS.length; index++) {
    const parts = skillLines[index + 1];
    if (!parts) {
      break;
    }
    stats[SKILLS[index].key] = { level: Number(parts[1]), xp: Number(parts[2]) };
  }
  return stats;
}

// Reads pasted hiscores in either format.
function parseHiscores(text) {
  const jsonStats = parseJsonHiscores(text);
  if (jsonStats) {
    return jsonStats;
  }
  return parseTextHiscores(text);
}

// Copies imported stats into the state. Returns how many skills were found.
// A skill you have not been ranked in has a rank of -1. In the JSON hiscores it still
// has a real level (1) and 0 XP, but some versions send -1 for the level or the XP as
// well, so for a level of -1 we use the XP if there is any, or else the minimum level.
function applyImportedStats(stats) {
  let importedCount = 0;

  for (const skill of SKILLS) {
    const entry = stats[skill.key];
    if (!entry) {
      continue;
    }

    const hasXp = entry.xp >= 0;
    let level = skill.minLevel;
    if (entry.level > 0) {
      level = entry.level;
    } else if (hasXp) {
      level = levelForXp(entry.xp);
    }
    level = clampLevel(level, skill.key);

    state.current[skill.key] = { level: level, xp: hasXp ? entry.xp : XP_FOR_LEVEL[level] };
    // Never leave a target below the level you have already reached.
    state.target[skill.key] = Math.max(state.target[skill.key], level);
    importedCount++;
  }

  return importedCount;
}

// The names of the skills that the imported stats did not include.
function namesOfSkillsNotFound(stats) {
  const names = [];
  for (const skill of SKILLS) {
    if (!stats[skill.key]) {
      names.push(skill.name);
    }
  }
  return names;
}

// The web address of the player's hiscores data, which the user opens in a new tab.
function hiscoreUrl() {
  const player = encodeURIComponent(state.username);
  return "https://secure.runescape.com/m=" + state.hiscoreMode +
    "/index_lite.json?player=" + player;
}


/* ============================================================================
   5. DRAWING THE PAGE
   Each function here reads the state and updates part of the page.
   (Strings written with `backticks` can contain ${values}, which makes it easy
   to build pieces of HTML.)
   ============================================================================ */

// Shortcut for finding an element by its id.
function byId(id) {
  return document.getElementById(id);
}

// 1234567 becomes "1,234,567".
function formatNumber(number) {
  return number.toLocaleString("en-US");
}

// 5 becomes "+5", -3 stays "-3", and 0 stays "0".
function formatChange(number) {
  return number > 0 ? "+" + number : String(number);
}

// The <option> tags for a drop-down list of every skill.
function skillOptionsHtml(selectedKey) {
  let html = "";
  for (const skill of SKILLS) {
    const selected = skill.key === selectedKey ? " selected" : "";
    html += `<option value="${skill.key}"${selected}>${skill.name}</option>`;
  }
  return html;
}

// Redraws everything that changes whenever the state changes.
// (The build rules list is drawn separately, by renderRules, because it only
// needs rebuilding when a rule is added or removed.)
function renderAll() {
  renderHeader();
  renderTrack();
  renderWorlds();
  renderRuleChecks();
  renderRoutePreferences();
  renderSkillRows();
}

// The title area: the rules summary line and the four totals.
function renderHeader() {
  const activeRules = [];
  for (const rule of state.rules) {
    if (rule.enabled) {
      activeRules.push(`${skillName(rule.skill)} max ${rule.max}`);
    }
  }
  if (state.untrimmed.enabled) {
    activeRules.push(`untrimmed ${skillName(state.untrimmed.skill)} cape`);
  }
  const preferenceSummary = chosenPreferenceSummary();
  if (preferenceSummary !== "") {
    activeRules.push(preferenceSummary);
  }
  byId("rule-summary").textContent =
    activeRules.length > 0 ? activeRules.join(", ") + "." : "No build rules checked.";

  byId("current-total").textContent = formatNumber(totalLevel(currentLevels()));
  byId("target-total").textContent = formatNumber(totalLevel(targetLevels()));
  byId("current-combat").textContent = combatLevel(currentLevels());
  byId("target-combat").textContent = combatLevel(targetLevels());
}

// How far along the bar (0 to 100 percent) a total level sits.
function trackPercent(total) {
  const highest = SKILLS.length * MAX_LEVEL;   // the maximum possible total level
  const limited = Math.max(0, Math.min(highest, total));
  return (limited / highest) * 100;
}

// The bar with a line for each world and a marker for current and target.
function renderTrack() {
  const current = totalLevel(currentLevels());
  const target = totalLevel(targetLevels());

  let gates = "";
  WORLD_THRESHOLDS.forEach(function (world, index) {
    // Every second label goes below the bar so close labels do not overlap.
    const labelClass = index % 2 === 1 ? "below" : "";
    gates += `<div class="track-gate" style="left:${trackPercent(world)}%">
                <span class="${labelClass}">${world}</span>
              </div>`;
  });

  byId("track").innerHTML = `
    <div class="track-groove"></div>
    <div class="track-fill" style="width:${trackPercent(target)}%"></div>
    ${gates}
    <div class="track-marker current" style="left:${trackPercent(current)}%"
         title="Current ${current}"></div>
    <div class="track-marker target" style="left:${trackPercent(target)}%"
         title="Target ${target}"></div>`;
}

// Creates one card per world. This runs once, when the page loads. Later,
// renderWorlds only updates the text inside the cards. If we rebuilt the
// cards every time, a click on a route button could be lost when it arrives
// at the same moment as an edited box loses focus.
function buildWorldCards() {
  let html = "";
  for (const world of WORLD_THRESHOLDS) {
    html += `
      <div class="world" data-world-card="${world}">
        <div class="world-title">${world} world</div>
        <div class="world-row"><span>Now</span><span data-status="now"></span></div>
        <div class="world-row"><span>At target</span><span data-status="target"></span></div>
        <div class="world-row warning unreachable"></div>
        <button type="button" data-world="${world}">Cheapest route to ${world}</button>
      </div>`;
  }
  byId("worlds").innerHTML = html;
}

// Shows "Unlocked (+12)" or "340 levels short" in a world card.
function showWorldStatus(element, total, world) {
  const difference = total - world;
  if (difference >= 0) {
    element.textContent = `Unlocked (+${difference})`;
    element.className = "good";
  } else {
    element.textContent = `${-difference} levels short`;
    element.className = "bad";
  }
}

// Updates every world card. A world the rules make impossible to reach
// shows a message instead of its route button.
function renderWorlds() {
  const reachable = maxTotalUnderRules();
  const current = totalLevel(currentLevels());
  const target = totalLevel(targetLevels());

  for (const card of byId("worlds").children) {
    const world = Number(card.dataset.worldCard);
    const canReach = world <= reachable;
    const unreachableNote = card.querySelector(".unreachable");

    showWorldStatus(card.querySelector('[data-status="now"]'), current, world);
    showWorldStatus(card.querySelector('[data-status="target"]'), target, world);
    unreachableNote.textContent = canReach ? "" : `Max ${reachable} under current rules`;
    unreachableNote.hidden = canReach;
    card.querySelector("button").hidden = !canReach;
  }
}

// The HTML for one level cap rule: a check box, a number box, and (for rules
// the user added) a Remove button. data-rule is the rule's position in
// state.rules, and data-field says which part of the rule an element is.
function ruleRowHtml(rule, index) {
  const name = skillName(rule.skill);
  const disabledClass = rule.enabled ? "" : " disabled";
  const checked = rule.enabled ? " checked" : "";
  const removeButton = rule.removable
    ? `<button type="button" class="small-button"
               data-rule="${index}" data-field="remove">Remove</button>`
    : "";

  return `
    <div class="rule${disabledClass}">
      <label class="checkbox-label">
        <input type="checkbox" data-rule="${index}" data-field="enabled"${checked}>
        ${name} max
      </label>
      <input type="number" min="1" max="${MAX_LEVEL}" value="${rule.max}"
             data-rule="${index}" data-field="max" aria-label="${name} maximum level">
      ${removeButton}
    </div>`;
}

// The HTML for the "untrimmed cape" rule, which is always the last one.
function untrimmedRuleHtml() {
  const untrimmed = state.untrimmed;
  const disabledClass = untrimmed.enabled ? "" : " disabled";
  const checked = untrimmed.enabled ? " checked" : "";

  return `
    <div class="rule${disabledClass}">
      <label class="checkbox-label">
        <input type="checkbox" data-field="untrimmed-enabled"${checked}>
        Untrimmed cape: no other 99 before 99
      </label>
      <select data-field="untrimmed-skill" aria-label="Skill for untrimmed cape">
        ${skillOptionsHtml(untrimmed.skill)}
      </select>
    </div>`;
}

// Draws the whole list of build rules. Only call this when the list itself
// changes (on load, or when a rule is added or removed). Changing a rule's
// check box or number does not need it, and rebuilding the list at the wrong
// moment can swallow a click on a Remove button.
function renderRules() {
  let html = "";
  state.rules.forEach(function (rule, index) {
    html += ruleRowHtml(rule, index);
  });
  html += untrimmedRuleHtml();
  byId("rules").innerHTML = html;
}

// Creates the route preference check boxes, one block per group. This runs once, when
// the page loads. renderRoutePreferences then ticks and unticks them in place.
function buildRoutePreferences() {
  let html = "";
  for (const group of PREFERENCE_GROUPS) {
    html += `<div class="preference-group-title">${group.title}</div>`;
    for (const preference of ROUTE_PREFERENCES) {
      if (preference.group !== group.id) {
        continue;
      }
      html += `
        <div class="rule">
          <label class="checkbox-label">
            <input type="checkbox" data-preference="${preference.id}">
            ${preference.label}
          </label>
          <span class="muted small">${preference.note}</span>
        </div>`;
    }
  }
  byId("route-preferences").innerHTML = html;
}

// Ticks the check box of each group's chosen preference and unticks the rest, so at
// most one per group is ever ticked. Unticked ones fade, like the other rules.
function renderRoutePreferences() {
  for (const checkbox of byId("route-preferences").querySelectorAll("input[data-preference]")) {
    const preference = findRoutePreference(checkbox.dataset.preference);
    const isChosen = state.routePreferences[preference.group] === preference.id;
    checkbox.checked = isChosen;
    checkbox.closest(".rule").classList.toggle("disabled", !isChosen);
  }
}

// The names of skills (other than the cape skill) that are at level 99.
function namesOfOtherMaxedSkills(levels, capeSkillKey) {
  const names = [];
  for (const skill of SKILLS) {
    if (skill.key !== capeSkillKey && levels[skill.key] >= MAX_LEVEL) {
      names.push(skill.name);
    }
  }
  return names;
}

// One line of the pass / fail messages: a coloured symbol and some text.
function checkLineHtml(cssClass, symbol, text) {
  return `<li class="${cssClass}">${symbol} ${text}</li>`;
}

// The pass / fail lines for the checked level caps: is each target within its cap?
function capCheckLines() {
  const lines = [];
  for (const rule of state.rules) {
    if (!rule.enabled) {
      continue;
    }
    const level = state.target[rule.skill];
    const text = `${skillName(rule.skill)} target ${level} (max ${rule.max})`;
    if (level <= rule.max) {
      lines.push(checkLineHtml("good", "✓", text));
    } else {
      lines.push(checkLineHtml("bad", "✗", text));
    }
  }
  return lines;
}

// The pass / fail lines for the untrimmed cape rule: no other skill may reach 99
// before the cape skill does.
function untrimmedCheckLines() {
  const lines = [];
  if (!state.untrimmed.enabled) {
    return lines;
  }

  const capeKey = state.untrimmed.skill;
  const capeName = skillName(capeKey);
  const maxedAtTarget = namesOfOtherMaxedSkills(targetLevels(), capeKey);
  const maxedNow = namesOfOtherMaxedSkills(currentLevels(), capeKey);
  const maxedNames = maxedAtTarget.join(", ");

  if (maxedAtTarget.length === 0) {
    lines.push(checkLineHtml("good", "✓", `No other 99 before ${capeName}`));
  } else if (state.target[capeKey] < MAX_LEVEL) {
    const text = `99 ${maxedNames} before 99 ${capeName} would trim the cape`;
    lines.push(checkLineHtml("bad", "✗", text));
  } else {
    const text = `99 ${capeName} and 99 ${maxedNames}: ` +
      `only untrimmed if ${capeName} was reached first`;
    lines.push(checkLineHtml("warning", "!", text));
  }

  if (maxedNow.length > 0 && state.current[capeKey].level < MAX_LEVEL) {
    lines.push(checkLineHtml("bad", "✗", `You already have 99 ${maxedNow.join(", ")}`));
  }
  return lines;
}

// The pass / fail messages under the build rules, plus the highest possible total.
function renderRuleChecks() {
  const lines = capCheckLines().concat(untrimmedCheckLines());
  byId("rule-checks").innerHTML =
    lines.length > 0 ? lines.join("") : `<li class="muted">No rules checked.</li>`;
  byId("max-total-note").textContent =
    `Highest total possible under these rules: ${maxTotalUnderRules()}.`;
}

// Creates the table rows, one per skill. This runs once, when the page loads.
// Later, renderSkillRows only updates what is inside them.
function buildSkillRows() {
  let html = "";
  for (const skill of SKILLS) {
    html += `
      <tr data-skill="${skill.key}">
        <td class="skill-name">${skill.name}</td>
        <td>
          <input type="number" class="current-input" min="${skill.minLevel}" max="${MAX_LEVEL}"
                 aria-label="${skill.name} current level">
        </td>
        <td>
          <span class="stepper">
            <button type="button" data-step="-1" aria-label="Lower ${skill.name} target">−</button>
            <input type="number" class="target-input" min="${skill.minLevel}" max="${MAX_LEVEL}"
                   aria-label="${skill.name} target level">
            <button type="button" data-step="1" aria-label="Raise ${skill.name} target">+</button>
          </span>
        </td>
        <td class="level-change"></td>
        <td class="xp-needed"></td>
        <td><input type="checkbox" class="lock-input" aria-label="Lock ${skill.name}"></td>
        <td class="cap-note"></td>
      </tr>`;
  }
  byId("skill-rows").innerHTML = html;
}

// Puts a value in a number box, unless the user is typing in it right now
// (overwriting it would be annoying).
function showValueUnlessTyping(input, value) {
  if (input !== document.activeElement) {
    input.value = value;
  }
}

// The text for the Cap column of one skill.
function capNoteText(skillKey) {
  const ruleCap = capFromRules(skillKey);
  if (ruleCap < MAX_LEVEL) {
    return `Max ${ruleCap}`;
  }
  if (capIncludingUntrimmed(skillKey) < MAX_LEVEL) {
    return "Max 98 (untrimmed)";
  }
  return "";
}

// Updates every row of the skills table, and the Total row at the bottom.
function renderSkillRows() {
  let totalXp = 0;

  for (const row of byId("skill-rows").rows) {
    const key = row.dataset.skill;
    const current = state.current[key].level;
    const target = state.target[key];
    const change = target - current;
    const xpNeeded = xpNeededForTarget(key);
    totalXp += xpNeeded;

    showValueUnlessTyping(row.querySelector(".current-input"), current);
    showValueUnlessTyping(row.querySelector(".target-input"), target);
    row.querySelector(".lock-input").checked = state.locked[key];

    const changeCell = row.querySelector(".level-change");
    changeCell.textContent = formatChange(change);
    changeCell.className = "level-change " + (change > 0 ? "good" : change < 0 ? "bad" : "");

    row.querySelector(".xp-needed").textContent = xpNeeded > 0 ? formatNumber(xpNeeded) : "";
    row.querySelector(".cap-note").textContent = capNoteText(key);
    row.classList.toggle("over-cap", target > capFromRules(key));
  }

  const currentTotal = totalLevel(currentLevels());
  const targetTotal = totalLevel(targetLevels());
  byId("footer-current").textContent = formatNumber(currentTotal);
  byId("footer-target").textContent = formatNumber(targetTotal);
  byId("footer-levels").textContent = formatChange(targetTotal - currentTotal);
  byId("footer-xp").textContent = formatNumber(totalXp);
}

// Points the "Open hiscores data" link at the player's hiscores, and hides
// the link until a username has been typed.
function updateHiscoreLink() {
  const link = byId("hiscore-link");
  link.href = hiscoreUrl();
  link.hidden = state.username === "";
}

// Shows a message in one of the message areas. The tone is "good", "warning", "bad" or "".
function setMessage(id, text, tone) {
  byId(id).textContent = text;
  byId(id).className = "note " + tone;
}

// Empties the two status messages (what the last route or import did).
function clearMessages() {
  setMessage("route-message", "", "");
  setMessage("import-message", "", "");
}


/* ============================================================================
   6. REACTING TO THE USER
   Each function below handles one kind of click or edit. They all follow the
   same pattern: change the state, then call saveAndRedraw().
   Section 7 connects them to the page.
   ============================================================================ */

// Saves the state, then redraws the page from it. It also clears the status messages,
// because after a change they may no longer be true ("Targets set for the 1500 world"
// is wrong once you edit a target). A handler that wants to show a message sets it
// after calling this.
function saveAndRedraw() {
  saveState();
  renderAll();
  clearMessages();
}

/* ----- The skills table ----- */

// A "change" event fires when the user finishes editing a box or ticks a check box.
function handleSkillTableChange(event) {
  const input = event.target;
  const row = input.closest("tr");
  if (!row) {
    return;
  }
  const key = row.dataset.skill;

  if (input.classList.contains("current-input")) {
    const level = clampLevel(parseInt(input.value, 10), key);
    state.current[key] = { level: level, xp: XP_FOR_LEVEL[level] };
    input.value = level;   // show the corrected value straight away
  } else if (input.classList.contains("target-input")) {
    input.value = state.target[key];   // show the corrected value
  } else if (input.classList.contains("lock-input")) {
    state.locked[key] = input.checked;
  }
  saveAndRedraw();
}

// An "input" event fires on every keystroke, so targets update as you type.
function handleSkillTableInput(event) {
  const input = event.target;
  if (!input.classList.contains("target-input")) {
    return;
  }
  const typedLevel = parseInt(input.value, 10);
  if (Number.isNaN(typedLevel)) {
    return;   // the box is empty for the moment, so wait
  }
  const key = input.closest("tr").dataset.skill;
  state.target[key] = clampLevel(typedLevel, key);
  saveAndRedraw();
}

// The - and + buttons next to each target.
function handleSkillTableClick(event) {
  const button = event.target.closest("button[data-step]");
  if (!button) {
    return;
  }
  const key = button.closest("tr").dataset.skill;
  const step = Number(button.dataset.step);   // -1 or +1
  state.target[key] = clampLevel(state.target[key] + step, key);
  saveAndRedraw();
}

/* ----- The four buttons above the skills table ----- */

function handleResetTargets() {
  for (const skill of SKILLS) {
    state.target[skill.key] = state.current[skill.key].level;
  }
  saveAndRedraw();
}

function handleMaxTargets() {
  for (const skill of SKILLS) {
    if (!state.locked[skill.key]) {
      const reachedLevel = state.current[skill.key].level;
      state.target[skill.key] = Math.max(reachedLevel, capIncludingUntrimmed(skill.key));
    }
  }
  saveAndRedraw();
}

function handleLockCombat() {
  for (const skillKey of COMBAT_SKILLS) {
    state.locked[skillKey] = true;
  }
  saveAndRedraw();
}

function handleUnlockAll() {
  for (const skill of SKILLS) {
    state.locked[skill.key] = false;
  }
  saveAndRedraw();
}

/* ----- The world cards ----- */

function handleWorldClick(event) {
  const button = event.target.closest("button[data-world]");
  if (!button) {
    return;
  }
  const goal = Number(button.dataset.world);
  const route = cheapestRoute(goal);

  for (const skill of SKILLS) {
    state.target[skill.key] = route.levels[skill.key];
  }
  saveAndRedraw();

  if (route.total < goal) {
    const message = `Can't reach ${goal} with these locks and rules. ` +
      `The highest is ${route.total}.`;
    setMessage("route-message", message, "bad");
  } else {
    const summary = chosenPreferenceSummary();
    const preferenceNote = summary === "" ? "" : `, ${summary}`;
    setMessage("route-message", `Targets set for the ${goal} world${preferenceNote}.`, "good");
  }
}

/* ----- The build rules ----- */

// The check boxes, number boxes and drop-down in the build rules. Their
// data-field attribute says which part of which rule changed. Nothing here
// rebuilds the rules list: we only fade the row in place.
function handleRuleChange(event) {
  const input = event.target;
  const field = input.dataset.field;
  const row = input.closest(".rule");

  if (field === "enabled") {
    const rule = state.rules[Number(input.dataset.rule)];
    rule.enabled = input.checked;
    row.classList.toggle("disabled", !rule.enabled);
  } else if (field === "max") {
    const rule = state.rules[Number(input.dataset.rule)];
    rule.max = clampRuleMax(parseInt(input.value, 10));
    input.value = rule.max;   // show the corrected value straight away
  } else if (field === "untrimmed-enabled") {
    state.untrimmed.enabled = input.checked;
    row.classList.toggle("disabled", !state.untrimmed.enabled);
  } else if (field === "untrimmed-skill") {
    state.untrimmed.skill = input.value;
  } else {
    return;   // not one of our fields
  }
  saveAndRedraw();
}

// The Remove button on rules the user added.
function handleRuleClick(event) {
  if (event.target.dataset.field !== "remove") {
    return;
  }
  state.rules.splice(Number(event.target.dataset.rule), 1);
  renderRules();   // later rules move up one place, so redraw the list
  saveAndRedraw();
}

// The "Add level cap" button. The new cap starts at the skill's current level.
function handleAddRule() {
  const skillKey = byId("new-rule-skill").value;
  state.rules.push({
    skill: skillKey,
    max: state.current[skillKey].level,
    enabled: true,
    removable: true,
  });
  renderRules();
  saveAndRedraw();
}

/* ----- Route preferences ----- */

// Ticking a preference makes it its group's chosen one, which unticks the other in that
// group (renderAll takes care of that). Unticking it leaves that group with no choice.
function handleRoutePreferenceChange(event) {
  const preference = findRoutePreference(event.target.dataset.preference);
  if (!preference) {
    return;
  }
  state.routePreferences[preference.group] = event.target.checked ? preference.id : null;
  saveAndRedraw();
}

/* ----- Loading stats ----- */

function handleUsernameInput(event) {
  state.username = event.target.value.trim();
  updateHiscoreLink();
  saveState();
}

function handleHiscoreModeChange(event) {
  state.hiscoreMode = event.target.value;
  updateHiscoreLink();
  saveState();
}

function handleImportClick() {
  const text = byId("hiscore-paste").value.trim();
  if (text === "") {
    setMessage("import-message", "Paste the hiscores page first.", "bad");
    return;
  }

  const stats = parseHiscores(text);
  const importedCount = applyImportedStats(stats);
  if (importedCount === 0) {
    const message = "Couldn't read any skills. Paste the full page from the hiscores link.";
    setMessage("import-message", message, "bad");
    return;
  }
  saveAndRedraw();

  // Say so if anything was missing, so a skill is never left out without you knowing.
  const notFound = namesOfSkillsNotFound(stats);
  if (notFound.length === 0) {
    setMessage("import-message", `Imported ${importedCount} skills.`, "good");
  } else {
    const message = `Imported ${importedCount} skills. ` +
      `Not found in the pasted data: ${notFound.join(", ")}.`;
    setMessage("import-message", message, "warning");
  }
}


/* ============================================================================
   7. START
   Connects each handler above to the page, then draws the page for the first time.
   ============================================================================ */

function connectEventHandlers() {
  // The skills table. Three kinds of event all land on the same table body.
  byId("skill-rows").addEventListener("change", handleSkillTableChange);
  byId("skill-rows").addEventListener("input", handleSkillTableInput);
  byId("skill-rows").addEventListener("click", handleSkillTableClick);

  byId("reset-targets").addEventListener("click", handleResetTargets);
  byId("max-targets").addEventListener("click", handleMaxTargets);
  byId("lock-combat").addEventListener("click", handleLockCombat);
  byId("unlock-all").addEventListener("click", handleUnlockAll);

  byId("worlds").addEventListener("click", handleWorldClick);

  byId("rules").addEventListener("change", handleRuleChange);
  byId("rules").addEventListener("click", handleRuleClick);
  byId("add-rule").addEventListener("click", handleAddRule);
  byId("route-preferences").addEventListener("change", handleRoutePreferenceChange);

  byId("username").addEventListener("input", handleUsernameInput);
  byId("hiscore-mode").addEventListener("change", handleHiscoreModeChange);
  byId("import-stats").addEventListener("click", handleImportClick);
}

function startUp() {
  // Fill in the parts of the page that depend on saved data.
  byId("new-rule-skill").innerHTML = skillOptionsHtml("strength");
  byId("username").value = state.username;
  byId("hiscore-mode").value = state.hiscoreMode;
  updateHiscoreLink();

  // Build the pieces that are created once, then draw everything.
  buildWorldCards();
  buildSkillRows();
  buildRoutePreferences();
  renderRules();
  renderAll();

  connectEventHandlers();
}

startUp();
