"use strict";

/* ============================================================================
   ROUTE PREFERENCES: the ratings you are free to change

   This file holds only data, no logic. It is loaded before script.js, which
   reads ROUTE_PREFERENCES to tilt the "cheapest route" buttons. If you want a
   route to favour different skills, this is the file to edit.

   HOW A RATING WORKS
   Each preference rates every skill from 0 to 3. Each rating point makes that
   skill's next levels count as half as expensive when a route decides what to
   train. On the OSRS XP curve, halving the cost is worth roughly 7 levels, so a
   skill rated 3 is favoured by about 20 levels over a skill rated 0.

   A rating can change as a skill levels up. Instead of one number, write
   bands: { 1: 0, 77: 2 } means "rated 0 from level 1, then rated 2 from level
   77". A plain number applies at every level.

   Every skill is listed in every preference, in the same order as the
   hiscores, so a skill is never left out by accident. The tests fail if one is
   missing.

   GROUPS AND COMBINING
   Each preference belongs to a group (see PREFERENCE_GROUPS below). Only one
   preference in a group can be ticked, but one from each group can be ticked
   together, for example "AFK" and "needs no supplies". When two are ticked, a
   skill counts for as much as the weaker of its two ratings. So it is only
   favoured if both preferences favour it: AFK together with no supplies means
   skills that are both. Ticking two never tilts a route harder than one.

   WHERE THE NUMBERS COME FROM
   Only the AFK ratings come from source data (see docs/afk-ratings.md, which
   also explains how to change them). The other preferences are opinions.
   ============================================================================ */

// How much each rating point discounts a skill's cost: 0.5 means half price.
const COST_FACTOR_PER_RATING_POINT = 0.5;

// The groups the preferences belong to. Only one preference in a group can be ticked,
// but one from each group can be ticked together.
const PREFERENCE_GROUPS = [
  { id: "activity", title: "How you want to train" },
  { id: "resources", title: "What you want to spend" },
];

const ROUTE_PREFERENCES = [
  {
    id: "afk",
    group: "activity",
    label: "Prefer AFK skills",
    note: "Favours skills that have AFK training methods at your level.",
    summary: "AFK skills",
    // Built from the OSRS Wiki page "Guide:AFK Skilling Methods" (revision 15358908).
    // The rating at each level depends on how long the best AFK method available at
    // that level keeps you AFK. docs/afk-ratings.md explains the rule and the
    // OVERRIDES marked below, and a test re-derives every other number from the wiki rows.
    ratings: {
      attack:        3,                              // crabs (all combat skills)
      defence:       3,                              // crabs
      strength:      3,                              // crabs
      hitpoints:     3,                              // crabs
      ranged:        3,                              // crabs
      prayer:        1,                              // auto-offering at a gilded altar
      magic:         3,                              // splashing
      cooking:       3,                              // OVERRIDE: see docs/afk-overrides.csv
      woodcutting:   { 1: 0, 45: 1, 60: 2, 75: 3 },  // maple 45, yew 60, magic tree 75
      fletching:     { 1: 0, 40: 1 },                // battlestaves from 40
      fishing:       { 1: 2, 38: 3 },                // general spots; cave eels from 38
      firemaking:    2,                              // Forester's campfire
      crafting:      1,                              // OVERRIDE: see docs/afk-overrides.csv
      smithing:      1,                              // one-bar items
      mining:        { 1: 0, 10: 3 },                // shooting stars from 10
      herblore:      { 1: 0, 11: 1 },                // making tar from 11
      agility:       0,                              // OVERRIDE: see docs/afk-overrides.csv
      thieving:      { 1: 0, 50: 2 },                // wealthy citizens from 50
      slayer:        2,                              // OVERRIDE: see docs/afk-overrides.csv
      farming:       0,                              // only recurring runs, which do not count
      runecraft:     { 1: 0, 77: 1 },                // Zeah blood runes from 77
      hunter:        0,                              // best methods are under 45 seconds
      construction:  1,                              // repair kits
      sailing:       { 1: 0, 40: 3 },                // OVERRIDE: see docs/afk-overrides.csv
    },
  },
  {
    id: "active",
    group: "activity",
    label: "Prefer active skills",
    note: "Favours skills you train by playing actively, not by waiting.",
    summary: "active skills",
    // An opinion. It starts as the mirror of the AFK ratings (3 minus the AFK rating at
    // every level), so a skill with no good AFK method counts as active. Change any
    // number you disagree with, for example if you think combat is active.
    ratings: {
      attack:        0,
      defence:       0,
      strength:      0,
      hitpoints:     0,
      ranged:        0,
      prayer:        2,
      magic:         0,
      cooking:       0,
      woodcutting:   { 1: 3, 45: 2, 60: 1, 75: 0 },
      fletching:     { 1: 3, 40: 2 },
      fishing:       { 1: 1, 38: 0 },
      firemaking:    1,
      crafting:      2,
      smithing:      2,
      mining:        { 1: 3, 10: 0 },
      herblore:      { 1: 3, 11: 2 },
      agility:       3,
      thieving:      { 1: 3, 50: 1 },
      slayer:        1,
      farming:       3,
      runecraft:     { 1: 3, 77: 2 },
      hunter:        3,
      construction:  2,
      sailing:       { 1: 3, 40: 0 },
    },
  },
  {
    id: "no-supplies",
    group: "resources",
    label: "Prefer skills that need no supplies",
    note: "Favours skills you can train without banked supplies. Suits ironmen.",
    summary: "skills that need no supplies",
    // An opinion, loosely based on the wiki's skill types: gathering and utility
    // skills need no prepared supplies, while production skills do.
    ratings: {
      attack:        3,
      defence:       3,
      strength:      3,
      hitpoints:     3,
      ranged:        2,
      prayer:        0,
      magic:         2,
      cooking:       0,
      woodcutting:   3,
      fletching:     0,
      fishing:       3,
      firemaking:    { 1: 0, 50: 3 },  // No supplies from 50 (Wintertodt); below 50 it burns logs
      crafting:      0,
      smithing:      0,
      mining:        3,
      herblore:      0,
      agility:       3,
      thieving:      3,
      slayer:        1,
      farming:       0,
      runecraft:     { 1: 0, 27: 3 },  // Guardians of the Rift from 27 needs no supplies
      hunter:        3,
      construction:  0,
      sailing:       3,
    },
  },
  {
    id: "buyable",
    group: "resources",
    label: "Prefer fast skills you can buy",
    note: "Favours skills that train fast when you spend money on them. Suits mains.",
    summary: "skills you can buy",
    // An opinion with no source data: how much faster a skill trains when you spend
    // money on it.
    ratings: {
      attack:        1,
      defence:       1,
      strength:      1,
      hitpoints:     1,
      ranged:        3,
      prayer:        3,
      magic:         3,
      cooking:       2,
      woodcutting:   0,
      fletching:     3,
      fishing:       0,
      firemaking:    1,
      crafting:      3,
      smithing:      3,
      mining:        0,
      herblore:      3,
      agility:       0,
      thieving:      0,
      slayer:        0,
      farming:       2,
      runecraft:     1,
      hunter:        0,
      construction:  3,
      sailing:       0,
    },
  },
];
