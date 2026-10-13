# OSRS Total Level Planner

A small web tool for planning which skills to train to reach an Old School RuneScape **total level world** (500, 750, 1250, 1500, 1750, 2000, 2200 and 2350).

It was built for restricted accounts (pures, hardcore ironmen, untrimmed Slayer cape runs) where some skills have to stay low, but it works for any account.

There is nothing to install and no server. It is a handful of small files: a page, a stylesheet and two scripts.

## What it does

- **Loads your stats** by pasting your hiscores page, or by typing levels in by hand.
- **Shows how far away each total level world is**, now and at your chosen targets.
- **Build rules** let you cap any skill (for example Attack at 75, Defence at 1, Prayer at 63). Rules only count while their box is ticked.
- **Untrimmed cape rule** stops any other skill reaching 99 before the skill you pick.
- **Cheapest route** buttons fill in targets that reach a world using the least total XP, while following your rules and leaving locked skills alone.
- **Route preferences** (optional) tilt the routes toward the skills that suit how you play. There are two groups: AFK skills or active skills, and skills that need no supplies or fast skills you can buy. You can tick one from each group, for example AFK skills that need no supplies, and a skill is then only favoured if both preferences favour it. The route then needs more total XP than the cheapest one, and the totals show by how much.
- **Lock** skills you have already decided on (for example your combat stats), so routes only change the rest.
- Shows **combat level** now and at your targets, and the XP still needed in every skill.

Your data is saved in your own browser and never leaves it. The page makes no network requests at all (the tests check this).

## Using it

1. Type your username, choose your account type, and click **Open hiscores data**. Copy everything on the page that opens.
2. Paste it into the box and click **Import stats**. (You can skip this and type levels into the Current column instead.)
3. Tick the **build rules** that apply to your account.
4. Set the targets you already know you want, and tick their **Lock** boxes. Lock any skill you do not want trained at its current level too, because the route is happy to raise a very low skill.
5. Optionally tick a **route preference**: AFK or active skills, and no supplies or buyable skills. You can tick one from each group. A preference tilts the route, it does not exclude any skill: one that is not favoured can still be trained, especially a very low one, so lock it if you want it left alone.
6. Click **Cheapest route** on the world you are aiming for. The Target column fills in.
7. Adjust any target with the **-** and **+** buttons or by typing, and watch the totals change.

The tool does not fetch the hiscores for you. You copy and paste them instead.

## Running it

Open `index.html` in any modern browser. That is all. Keep `index.html`, `style.css`, `route-preferences.js` and `script.js` in the same folder, because the page loads the other three by name.

To host it for others, upload the folder to any static host, for example [Netlify Drop](https://app.netlify.com/drop) (drag the folder onto the page) or GitHub Pages (push the folder to a repository and turn on Pages in its settings).

## Running the tests

The tests open the page in a real browser and click through it. You need Python 3 and a one-time setup:

```
pip install playwright
playwright install chromium
```

Then, from this folder:

```
python tests/run_tests.py
```

Each check prints `PASS` or `FAIL`, and the script exits with an error if any fail. To test a different copy of the page, pass its path: `python tests/run_tests.py path/to/index.html`. The tests also check the AFK ratings against the wiki data in `docs/afk-methods.csv`.

## Project layout

```
index.html              The page structure
style.css               All of the visual styling
route-preferences.js    The route preference ratings: data you are free to edit
script.js               All of the behaviour: the sums, the saving, drawing the page
docs/afk-ratings.md     Where the AFK ratings come from, and how to change them
docs/afk-methods.csv    The wiki's AFK methods, one per row
docs/afk-overrides.csv  AFK ratings set by hand instead of by the rule
tests/run_tests.py      Browser tests
LICENSE                 MIT license
```

## Reading the code

The code is written so that someone new to programming can follow it. Start with `index.html` to see the page structure, then read `script.js` from top to bottom. (The editable route preference ratings are kept apart in `route-preferences.js`, so you can change them without reading any logic.) The script is split into seven numbered sections, from fixed game data down to the startup code, and each only uses things from the sections above it.

The whole tool follows one loop:

> the user does something, **then** the state changes, **then** the state is saved, **then** the whole page is redrawn from the state.

The `state` object (section 2 of the script) holds everything the user has entered, and is documented with an example.

### Common changes

| I want to... | Change this |
| --- | --- |
| Add or remove a total level world | `WORLD_THRESHOLDS` in `script.js`. The cards and the bar update by themselves. (Also update the "one card per world" test.) |
| Change colours or the font | The variables at the top of `style.css`. |
| Change which skills count as AFK, active, supply-free or buyable | `ROUTE_PREFERENCES` in `route-preferences.js`. For the AFK ratings also read `docs/afk-ratings.md`, because a test checks them against the wiki data. Every skill has a rating from 0 to 3 for each preference. Each point makes a skill's levels count as half as expensive, which is worth about 7 levels. A rating can also be written as bands, such as `{ 1: 0, 77: 2 }`, meaning 0 from level 1 and 2 from level 77. |
| Change which level caps are always shown | `DEFAULT_RULE_SKILLS` in `script.js`. |
| Add a skill the game adds | `SKILL_NAMES` in `script.js`. Keep it in the same order as the official hiscores list, because the plain text import depends on that order. |

## Where to find each feature

A feature touches several parts of `script.js`, because the code is arranged by what it does (data, calculations, drawing, reacting) rather than by feature. This table lists where each one lives. A test checks that every name below really exists.

| Feature | Where to look |
| --- | --- |
| Level caps and the untrimmed cape rule | Section 3: `capFromRules`, `capIncludingUntrimmed`. Drawn by `renderRules` (section 5) and changed by `handleRuleChange` (section 6). |
| The cheapest route | Section 3: `cheapestRoute`. Started by `handleWorldClick` (section 6). |
| Route preferences | The ratings are in `route-preferences.js`. Section 1: `findRoutePreference`. Section 3: `chosenPreferences`, `ratingAtLevel`, `routeCostFactor`. Section 5: `renderRoutePreferences`. Section 6: `handleRoutePreferenceChange`. |
| Saving and loading | Section 2: `saveState`, `loadState`. |
| Importing hiscores | Section 4: `parseHiscores`, `applyImportedStats`. Started by `handleImportClick` (section 6). |
| The world cards and the bar | Section 5: `renderWorlds`, `renderTrack`. The list of worlds is `WORLD_THRESHOLDS` (section 1). |

## Contributing

Issues and pull requests are welcome. Please run the tests before sending a change, and add a test for anything new. To keep the code friendly to beginners, prefer plain names over short ones, keep functions small, and write comments that explain why something is done, not only what it does. Keep lines to 100 characters or fewer. The Python tests are formatted with `black -l 100 tests/run_tests.py`.

## Notes

- It was tested in Chromium (Chrome and Edge). Firefox and Safari should work, because the code uses nothing exotic, but they have not been tested.
- The hiscores import reads the JSON page or the older plain-text page. It matches skills by name, and by position if a name is not recognised. If any skill is missing, the message under the Import button names it.
- The world list is for **members** total level worlds. Free-to-play total level worlds do not count members skills, and this tool counts every skill.
- The route preference ratings are judgement calls, not game data. The AFK ratings come from the wiki's [AFK Skilling Methods guide](https://oldschool.runescape.wiki/w/Guide:AFK_Skilling_Methods?oldid=15358908), worked out by a fixed rule that you can read and re-run: see [docs/afk-ratings.md](docs/afk-ratings.md). A test checks every AFK number against the wiki rows in `docs/afk-methods.csv`, and the exceptions made by hand are listed, with reasons, in `docs/afk-overrides.csv`. The "active", "no supplies" and "buyable" ratings are opinions with no source data, and "active" started as the mirror of the AFK ratings. Edit the ratings to match your own view.
- Without a route preference, routes pick the fewest total XP, not the fastest way to train, so skills with cheap levels fill up first. With a preference ticked, routes favour the skills it rates highly and need more total XP.
- Game data (the experience table, the combat level formula and the world list) comes from the [OSRS Wiki](https://oldschool.runescape.wiki/).

## License

MIT. See [LICENSE](LICENSE).

Old School RuneScape and RuneScape are trademarks of Jagex Ltd. This is an unofficial fan-made tool and is not affiliated with or endorsed by Jagex.
