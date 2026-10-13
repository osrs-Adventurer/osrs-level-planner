# How the route preference ratings were made

The ratings live in [`route-preferences.js`](../route-preferences.js). There are four preferences, in two groups, and they do not all have the same standing:

| Preference | Where the numbers come from |
| --- | --- |
| Prefer AFK skills | **Source data.** Worked out by a fixed rule from the OSRS Wiki's AFK guide. This page explains the rule, and a test re-checks every number. |
| Prefer active skills | **Opinion.** It started as the mirror of the AFK ratings (3 minus the AFK rating at every level), so a skill with no good AFK method counts as active. It is not kept in step with the AFK table afterwards, so edit it by hand. |
| Prefer skills that need no supplies | **Opinion**, loosely based on the wiki's skill types: gathering and utility skills need no prepared supplies, production skills do. |
| Prefer fast skills you can buy | **Opinion.** There is no source data. |

Only the AFK ratings can be audited. The others are judgement calls and are labelled that way in the code.

The preferences are in two groups: AFK or active, and no supplies or buyable. Only one in a group can be ticked, but one from each group can be ticked together. When two are ticked, a skill counts for as much as the weaker of its two ratings, so it is only favoured when both preferences favour it: AFK together with no supplies means skills that are both. The tilt is never stronger than with one preference, and a test checks this.

## The AFK ratings

### Source

The OSRS Wiki page [Guide:AFK Skilling Methods](https://oldschool.runescape.wiki/w/Guide:AFK_Skilling_Methods), **revision 15358908** (read in October 2026). The permanent link to exactly that version is:

<https://oldschool.runescape.wiki/w/Guide:AFK_Skilling_Methods?oldid=15358908>

The page changes over time, so always compare against that revision, not the live page.

### The method list

[`afk-methods.csv`](afk-methods.csv) has every row of the page's three tables, in the page's order, so you can compare the two side by side. It opens in any spreadsheet program.

| Column | Meaning |
| --- | --- |
| `section` | `skilling`, `combat` or `recurring`: which of the page's tables the row is from. |
| `applies_to` | The skill. In the combat table it can also be `all-combat` (every combat skill) or `melee` (Attack, Strength, Defence and Hitpoints). |
| `level` | The lowest level the method needs. For combat methods this is the page's recommended level. Upper ends of ranges, and requirements in other skills, are in the `note` column and are **not** used. |
| `afk_time` | How long the method keeps you AFK. For `recurring` rows it is how often you come back instead. |
| `exp_per_hour` | The page's exp/h figure. The page says these assume level 99 and optimal gear, so treat them as maximums. |

The file has 73 skilling methods, 13 combat methods and 4 recurring methods, the same as the page. It also has some extra rows: second rows the page shows for the same method, and bonus XP in another skill. Rows with no `afk_time` can never count.

**This file was typed in by hand.** The tools used to build this project cannot download the wiki page, so a mistake is possible. To check, compare some rows with the revision above.

### The rule

1. A method **counts** if it is in the `skilling` or `combat` table (never `recurring`), keeps you AFK for **at least 45 seconds**, and gives **at least 10,000 exp/h**.
2. The rating at a level comes from the **longest AFK time** among the counted methods that need that level or lower:
   - **3** for 3.5 minutes or more
   - **2** for 1.5 minutes or more
   - **1** for anything shorter
   - **0** if no method counts
3. A skill's rating can therefore rise as it levels up. In the code that is written as bands. For example `{ 1: 0, 77: 1 }` means 0 from level 1 and 1 from level 77.

The 45 seconds is a choice, not the wiki's. The wiki's own minimum is one minute, but that would leave out Zeah runecrafting (55 seconds). 45 seconds lets it count, and still leaves out ZMI runecrafting (25 seconds).

Recurring methods, such as farming runs, are a different kind of thing: they are chores you return to, not training you can leave running. So they are not counted.

### The overrides

[`afk-overrides.csv`](afk-overrides.csv) lists the ratings that are set by hand instead of by the rule. Each row has four columns: the `skill`, the level it starts `from_level` (use 1 for every level), the `rating`, and the `reason`. A skill can have several rows, one for each band. Below a skill's first row, the rule still applies, so you only list what you change. The rows today are:

- **Agility** is 0 at every level. The page lists Agility methods, and the rule alone would rate it 3 from level 1 because of a 10-minute method at 12,000 exp/h, which needs 88 Construction. The maintainer decided Agility's exp rates are too slow to count.
- **Slayer** is 2 at every level. It is not on the page, so the rule would give 0. The rating is kept from the first draft.
- **Crafting** is 1 at every level. The rule gives 2, because of firing clay (1:58). The maintainer's reason is that nobody trains Crafting with pottery, because making the unfired pots by hand is tedious.
- **Cooking** is 3 at every level. The rule only gives 3 from level 21, because the page lists cooking fish at 1:07 and churning from 21. The maintainer's reason is that Cooking is AFK from level 1 to 99: you put food in the inventory and wait for it to cook, and it is commonly known as an AFK skill.
- **Sailing** is 0 until level 40, then 3. The rule would give 2 from level 35 because of the barracuda wrecks. The maintainer's reason is that Sailing counts as AFK from level 40, because crewmate salvaging stays AFK all the way to 99. This takes two rows in the CSV, because an override carries on upward until the next row, so the level 40 row ends the 0 band.

### How the check works

The test `test_afk_ratings_match_the_wiki_data` in [`tests/run_tests.py`](../tests/run_tests.py) reads the two CSV files, applies the rule above to every skill at every level from 1 to 99, and compares the result with the AFK ratings the page really uses. It fails, and names the skill and level, if any number differs.

### Changing an AFK rating

Because the test checks every number, you cannot change an AFK rating quietly. Choose one of these:

- **You disagree with the rule.** Change the thresholds at the top of the AFK section of `tests/run_tests.py`, then update the numbers in `route-preferences.js` to match.
- **The wiki page changed.** Update `afk-methods.csv` and the revision number in this file and in `route-preferences.js`, then update the ratings the test reports as different.
- **You just disagree with one skill's rating.** Add a row to `afk-overrides.csv` with the level it starts from, the rating and your reason, and change the number in `route-preferences.js` to match. For a rating that changes with level, add one row for each band. That keeps the exception visible instead of hidden.
