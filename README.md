# OSRS Total Level Planner

A small web tool for planning which skills to train to reach an Old School RuneScape **total level world** (500, 750, 1250, 1500, 1750, 2000, 2200 and 2350).

It was built for restricted accounts (pures, hardcore ironmen, untrimmed Slayer cape runs) where some skills have to stay low, but it works for any account.

There is nothing to install and no server. It is three small files: a page, a stylesheet and a script.

## What it does

- **Loads your stats** by pasting your hiscores page, or by typing levels in by hand.

- **Shows how far away each total level world is**, now and at your chosen targets.

- **Build rules** let you cap any skill (for example Attack at 75, Defence at 1, Prayer at 63). Rules only count while their box is ticked.

- **Untrimmed cape rule** stops any other skill reaching 99 before the skill you pick.

- **Cheapest route** buttons fill in targets that reach a world using the least total XP, while following your rules and leaving locked skills alone.

- **Lock** skills you have already decided on (for example your combat stats), so routes only change the rest.

- Shows **combat level** now and at your targets, and the XP still needed in every skill.

Your data is saved in your own browser and never leaves it. The page makes no network requests at all (the tests check this).

## Using it

1. Type your username, choose your account type, and click **Open hiscores data**. Copy everything on the page that opens.

2. Paste it into the box and click **Import stats**. (You can skip this and type levels into the Current column instead.)

3. Tick the **build rules** that apply to your account.

4. Set the targets you already know you want, and tick their **Lock** boxes.

5. Click **Cheapest route** on the world you are aiming for. The Target column fills in.

6. Adjust any target with the **-** and **+** buttons or by typing, and watch the totals change.

The tool does not fetch the hiscores for you. You copy and paste them instead.

## Running it

Open `index.html` in any modern browser. That is all. Keep `index.html`, `style.css` and `script.js` in the same folder, because the page loads the other two by name.

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

Each check prints `PASS` or `FAIL`, and the script exits with an error if any fail. To test a different copy of the page, pass its path: `python tests/run_tests.py path/to/index.html`.

## Project layout

```
index.html           The page structure
style.css            All of the visual styling
script.js            All of the behaviour: the sums, the saving, drawing the page
tests/run_tests.py   Browser tests
LICENSE              MIT license
```

## Reading the code

The code is written so that someone new to programming can follow it. Start with `index.html` to see the page structure, then read `script.js` from top to bottom. The script is split into seven numbered sections, from fixed game data down to the startup code, and each only uses things from the sections above it.

The whole tool follows one loop:

> the user does something, **then** the state changes, **then** the state is saved, **then** the whole page is redrawn from the state.

The `state` object (section 2 of the script) holds everything the user has entered, and is documented with an example.

### Common changes

| I want to... | Change this |
| - | - |
| Add or remove a total level world | `WORLD_THRESHOLDS` in `script.js`. The cards and the bar update by themselves. (Also update the "one card per world" test.) |
| Change colours or the font | The variables at the top of `style.css`. |
| Change which level caps are always shown | `DEFAULT_RULE_SKILLS` in `script.js`. |
| Add a skill the game adds | `SKILL_NAMES` in `script.js`. Keep it in the same order as the official hiscores list, because the plain text import depends on that order. |


## Contributing

Issues and pull requests are welcome. Please run the tests before sending a change, and add a test for anything new. To keep the code friendly to beginners, prefer plain names over short ones, keep functions small, and write comments that explain why something is done, not only what it does.

## Notes

- The world list is for **members** total level worlds. Free-to-play total level worlds do not count members skills, and this tool counts every skill.

- Routes pick the fewest total XP, not the fastest way to train. Skills with cheap levels fill up first.

- Game data (the experience table, the combat level formula and the world list) comes from the [OSRS Wiki](https://oldschool.runescape.wiki/).

## License

MIT. See [LICENSE](file:///home/dyl/Desktop/Anonymous_Adventurer/tools/osrs-total-level-planner/LICENSE).

Old School RuneScape and RuneScape are trademarks of Jagex Ltd. This is an unofficial fan-made tool and is not affiliated with or endorsed by Jagex.

## A note on AI usage

I used Claude when writing this application. I have been a professional software developer since 2018. I wrote the application to be as human-auditable as I could.

