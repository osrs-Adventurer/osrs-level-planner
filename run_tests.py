"""
Browser tests for the OSRS total level planner.

These tests open index.html in a real (invisible) Chromium browser, click and
type like a person would, and check what appears on the page.

How to run them
---------------
One-time setup (needs Python 3):

    pip install playwright
    playwright install chromium

Then, from the project folder:

    python tests/run_tests.py

To test a different copy of the page, give its path:

    python tests/run_tests.py path/to/index.html

Every check prints PASS or FAIL. The script ends with an error code if any
check failed, so it can also be used in automated builds.

How this file is organised
--------------------------
1. Settings and sample data
2. Helpers: "Planner" (clicks and reads the page) and "check" (records results)
3. The tests, grouped by feature. Each group starts from a fresh, empty page.
4. main(): runs every group and prints the summary
"""

import csv
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# =============================================================================
# 1. SETTINGS AND SAMPLE DATA
# =============================================================================

# The project folder is the one above this file. By default, test its index.html.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DEFAULT_PAGE = PROJECT_FOLDER / "index.html"
DOCS_FOLDER = PROJECT_FOLDER / "docs"

# The name the page saves its data under in the browser (see STORAGE_KEY in script.js).
STORAGE_KEY = "osrs-level-planner-v1"

# A made-up account, listed in the same order as the hiscores.
SAMPLE_LEVELS = {
    "attack": 60,
    "defence": 1,
    "strength": 37,
    "hitpoints": 35,
    "ranged": 48,
    "prayer": 43,
    "magic": 49,
    "cooking": 70,
    "woodcutting": 60,
    "fletching": 55,
    "fishing": 62,
    "firemaking": 50,
    "crafting": 45,
    "smithing": 70,
    "mining": 60,
    "herblore": 40,
    "agility": 50,
    "thieving": 55,
    "slayer": 44,
    "farming": 45,
    "runecraft": 40,
    "hunter": 50,
    "construction": 40,
    "sailing": 1,
}
SAMPLE_TOTAL = sum(SAMPLE_LEVELS.values())

COMBAT_SKILLS = ["attack", "defence", "strength", "hitpoints", "ranged", "prayer", "magic"]

# The order the built-in level caps appear in the "Build rules" section.
RULE_ORDER = ["attack", "strength", "defence", "hitpoints", "ranged", "magic", "prayer"]


# ----- The rule that turns the wiki's AFK methods into AFK ratings -----
# docs/afk-ratings.md explains this rule. If you change a number here, update that file
# and the AFK numbers in route-preferences.js too.
MIN_AFK_SECONDS = 45  # a method must keep you AFK for at least this long to count
MIN_EXP_PER_HOUR = 10_000  # and give at least this much exp/h
THREE_POINT_SECONDS = 210  # rating 3 from this AFK time (3.5 minutes)
TWO_POINT_SECONDS = 90  # rating 2 from this AFK time (1.5 minutes), otherwise 1

# In the combat table, some rows apply to several skills at once.
COMBAT_GROUPS = {
    "all-combat": ["attack", "strength", "defence", "hitpoints", "ranged", "magic"],
    "melee": ["attack", "strength", "defence", "hitpoints"],
}


def build_xp_table():
    """The OSRS experience formula, written out again here so these tests do
    not simply trust the page's own numbers. xp_for_level[50] is the total XP
    needed for level 50."""
    table = [0, 0]
    points = 0
    for level in range(1, 99):
        points += int(level + 300 * 2 ** (level / 7))
        table.append(points // 4)
    return table


XP_FOR_LEVEL = build_xp_table()

# A little extra XP on top of each level, so the tests prove the page uses the
# real XP from the hiscores and not just the level.
EXTRA_XP = 123


def hiscores_data():
    """The sample account as a dictionary, written the way the JSON hiscores look.
    Sailing is left unranked (-1), as it is for players who have never trained it."""
    skills = [{"id": 0, "name": "Overall", "rank": 1, "level": SAMPLE_TOTAL, "xp": 1}]
    for number, (skill, level) in enumerate(SAMPLE_LEVELS.items(), start=1):
        skills.append(
            {
                "id": number,
                "name": skill.capitalize(),
                "rank": 5,
                "level": level,
                "xp": XP_FOR_LEVEL[level] + EXTRA_XP,
            }
        )
    skills[-1]["level"] = -1
    skills[-1]["xp"] = -1
    return {"skills": skills, "activities": []}


def hiscores_json():
    """The same account as text, ready to paste."""
    return json.dumps(hiscores_data())


def hiscores_text():
    """The sample account in the older plain text format ("rank,level,xp" per
    line), with every level one higher and some minigame lines at the end."""
    lines = ["1,%d,999" % SAMPLE_TOTAL]
    for level in SAMPLE_LEVELS.values():
        lines.append("5,%d,%d" % (level + 1, XP_FOR_LEVEL[level + 1]))
    lines += ["-1,-1", "12,300"]
    return "\n".join(lines)


# =============================================================================
# 2. HELPERS
# =============================================================================

results = []  # one (name, passed, detail) entry per check


def check(name, condition, detail=""):
    """Records one result. 'detail' is shown only when the check fails."""
    results.append((name, bool(condition), detail))


def run_group(test_function, *arguments):
    """Runs one group of tests. If the group crashes (for example because a
    box it expected is missing), that is recorded as a failure and the other
    groups still run."""
    try:
        test_function(*arguments)
    except Exception as error:
        check(test_function.__name__ + " finished without crashing", False, repr(error))


class Planner:
    """Wraps the browser page with small, readable actions such as
    set_target("attack", 75). Tests use this instead of raw selectors."""

    def __init__(self, page, page_url):
        self.page = page
        self.page_url = page_url

    # ----- opening and reading -----

    def open_fresh(self):
        """Opens the page with nothing saved, like a first-time visitor."""
        self.page.goto(self.page_url)
        self.page.evaluate("localStorage.clear()")
        self.page.reload()

    def text(self, selector):
        return self.page.inner_text(selector).strip()

    def value(self, selector):
        return self.page.input_value(selector)

    # ----- the skills table -----

    @staticmethod
    def row(skill):
        return "tr[data-skill=%s]" % skill

    def type_number(self, selector, number):
        """Types a number into a box and then leaves it, which is when the
        page treats the edit as finished."""
        self.page.fill(selector, str(number))
        self.page.dispatch_event(selector, "change")

    def set_current(self, skill, level):
        self.type_number(self.row(skill) + " .current-input", level)

    def set_target(self, skill, level):
        self.type_number(self.row(skill) + " .target-input", level)

    def current(self, skill):
        return int(self.value(self.row(skill) + " .current-input"))

    def target(self, skill):
        return int(self.value(self.row(skill) + " .target-input"))

    def click_step(self, skill, direction):
        """Clicks the - (direction -1) or + (direction 1) button for a skill."""
        self.page.click('%s button[data-step="%d"]' % (self.row(skill), direction))

    def is_locked(self, skill):
        return self.page.is_checked(self.row(skill) + " .lock-input")

    def toggle_lock(self, skill):
        self.page.click(self.row(skill) + " .lock-input")

    def lock_everything_except(self, kept_skill):
        for skill in SAMPLE_LEVELS:
            if skill != kept_skill and not self.is_locked(skill):
                self.toggle_lock(skill)

    # ----- the four buttons above the table -----

    def reset_targets(self):
        self.page.click("#reset-targets")

    def max_targets(self):
        self.page.click("#max-targets")

    def lock_combat(self):
        self.page.click("#lock-combat")

    def unlock_all(self):
        self.page.click("#unlock-all")

    # ----- worlds -----

    def click_world(self, world):
        self.page.click('button[data-world="%d"]' % world)

    # ----- build rules -----

    @staticmethod
    def rule_selector(skill, field):
        return '#rules input[data-rule="%d"][data-field=%s]' % (RULE_ORDER.index(skill), field)

    def set_rule(self, skill, max_level, enabled=True):
        """Sets the level in a built-in cap rule and switches it on or off."""
        self.type_number(self.rule_selector(skill, "max"), max_level)
        checkbox = self.rule_selector(skill, "enabled")
        if self.page.is_checked(checkbox) != enabled:
            self.page.click(checkbox)

    def toggle_untrimmed(self):
        self.page.click("#rules input[data-field=untrimmed-enabled]")

    def rule_count(self):
        return self.page.locator("#rules .rule").count()

    # ----- route preferences -----

    @staticmethod
    def preference_box(preference_id):
        return '#route-preferences input[data-preference="%s"]' % preference_id

    def click_preference(self, preference_id):
        self.page.click(self.preference_box(preference_id))

    def ticked_preferences(self):
        """The ids of the preferences whose check box is ticked."""
        return self.page.eval_on_selector_all(
            "#route-preferences input:checked", "boxes => boxes.map(box => box.dataset.preference)"
        )

    def all_targets(self):
        return {skill: self.target(skill) for skill in SAMPLE_LEVELS}

    def rating_tables(self):
        """The ratings as written in route-preferences.js: preference id -> skill -> rating."""
        return self.page.evaluate(
            "Object.fromEntries(ROUTE_PREFERENCES.map(p => [p.id, p.ratings]))"
        )

    def ratings_by_level(self):
        """Every rating at every level: preference id -> skill -> a list for levels 1 to 99."""
        return self.page.evaluate("""() => Object.fromEntries(ROUTE_PREFERENCES.map(p => [p.id,
            Object.fromEntries(SKILLS.map(s => [s.key,
                Array.from({length: 99},
                    (_, index) => ratingAtLevel(p.ratings[s.key], index + 1))]))]))""")

    # ----- importing -----

    def import_text(self, text):
        self.page.fill("#hiscore-paste", text)
        self.page.click("#import-stats")

    def import_sample_stats(self):
        self.import_text(hiscores_json())
        self.reset_targets()

    # ----- saving -----

    def save_raw(self, saved_value):
        """Writes a value straight into the browser's saved data, as an older
        version of the tool (or a damaged save) would have left it."""
        self.page.evaluate(
            "([key, value]) => localStorage.setItem(key, value)",
            [STORAGE_KEY, saved_value],
        )
        self.page.reload()


def average(numbers):
    return sum(numbers) / len(numbers)


def read_csv(file_name):
    """Reads a CSV file from the docs folder as a list of dictionaries."""
    with open(DOCS_FOLDER / file_name, newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def seconds(time_text):
    """Turns a time such as "07:17" (minutes and seconds) into seconds."""
    minutes, secs = time_text.split(":")
    return int(minutes) * 60 + int(secs)


def skills_for(applies_to):
    """The skills a row of the methods file applies to."""
    return COMBAT_GROUPS.get(applies_to, [applies_to])


def derive_afk_rating(methods, skill, level):
    """The AFK rating the rule gives a skill at a level, from the wiki's methods."""
    longest_afk = 0
    for method in methods:
        if method["section"] == "recurring" or skill not in skills_for(method["applies_to"]):
            continue
        if int(method["level"]) > level:
            continue
        if method["afk_time"] == "" or method["exp_per_hour"] == "":
            continue  # extra XP rows have no AFK time of their own
        afk_seconds = seconds(method["afk_time"])
        if afk_seconds >= MIN_AFK_SECONDS and int(method["exp_per_hour"]) >= MIN_EXP_PER_HOUR:
            longest_afk = max(longest_afk, afk_seconds)

    if longest_afk == 0:
        return 0
    if longest_afk >= THREE_POINT_SECONDS:
        return 3
    if longest_afk >= TWO_POINT_SECONDS:
        return 2
    return 1


def read_overrides():
    """The hand-set AFK ratings: skill -> list of (from_level, rating), lowest level first."""
    overrides = {}
    for row in read_csv("afk-overrides.csv"):
        bands = overrides.setdefault(row["skill"], [])
        bands.append((int(row["from_level"]), int(row["rating"])))
        bands.sort()
    return overrides


def override_rating_at(bands, level):
    """The rating an override gives at a level, or None if it has not started yet."""
    result = None
    for from_level, rating in bands:
        if from_level <= level:
            result = rating
    return result


def rating_at(ratings, skill, level):
    """ratings[skill] is a list with one rating for each level from 1 to 99."""
    return ratings[skill][level - 1]


def rating_is_valid(rating):
    """A rating is a number from 0 to 3, or bands like {"1": 0, "77": 2} whose
    start levels are 1 to 99 and whose ratings are 0 to 3."""
    if isinstance(rating, dict):
        return all(
            start.isdigit() and 1 <= int(start) <= 99 and value in (0, 1, 2, 3)
            for start, value in rating.items()
        )
    return rating in (0, 1, 2, 3)


# =============================================================================
# 3. THE TESTS
# =============================================================================


def test_fresh_page(planner):
    """What a first-time visitor sees."""
    planner.open_fresh()

    check("fresh: current total is 33", planner.text("#current-total") == "33")
    check("fresh: combat level is 3", planner.text("#current-combat") == "3")
    check("fresh: no rules are active", "No build rules checked" in planner.text("#rule-summary"))

    caps = planner.page.eval_on_selector_all(
        "#rules input[data-field=max]", "inputs => inputs.map(input => input.value)"
    )
    check(
        "fresh: seven combat caps start at the skill minimum",
        caps == ["1", "1", "1", "10", "1", "1", "1"],
        str(caps),
    )

    rule_text = planner.text("#rules")
    check(
        "fresh: combat caps are listed in order",
        all(
            name + " max" in rule_text
            for name in ["Attack", "Strength", "Defence", "Hitpoints", "Ranged", "Magic", "Prayer"]
        ),
    )
    check(
        "fresh: built-in caps cannot be removed",
        planner.page.locator("#rules button[data-field=remove]").count() == 0,
    )
    check(
        "fresh: highest possible total is 2376",
        "2376" in planner.text("#max-total-note"),
        planner.text("#max-total-note"),
    )
    check("fresh: there is one card per world", planner.page.locator(".world").count() == 8)

    check(
        "fresh: route-preferences.js is loaded",
        planner.page.evaluate("typeof ROUTE_PREFERENCES") == "object",
    )

    # If style.css failed to load, the page would have a white background.
    background = planner.page.evaluate("getComputedStyle(document.body).backgroundColor")
    check("fresh: style.css is loaded", background == "rgb(15, 10, 10)", background)


def test_json_import(planner):
    planner.open_fresh()
    planner.import_text(hiscores_json())

    check(
        "json import: reports 24 skills",
        "Imported 24" in planner.text("#import-message"),
        planner.text("#import-message"),
    )
    check(
        "json import: total level is right",
        planner.text("#current-total") == "{:,}".format(SAMPLE_TOTAL),
        planner.text("#current-total"),
    )
    check("json import: an unranked skill becomes level 1", planner.current("sailing") == 1)
    # base 0.25 x (1 + 35 + 21) = 14.25, melee 0.325 x (60 + 37) = 31.525, total 45.77
    check(
        "json import: combat level is 45",
        planner.text("#current-combat") == "45",
        planner.text("#current-combat"),
    )
    check(
        "json import: targets are never below current levels",
        all(planner.target(skill) >= level for skill, level in SAMPLE_LEVELS.items()),
    )


def test_json_import_with_odd_data(planner):
    """The import must never drop a skill without saying so."""
    planner.open_fresh()

    # A skill spelled differently (the real hiscores might say "Runecrafting").
    data = hiscores_data()
    for entry in data["skills"]:
        if entry["name"] == "Runecraft":
            entry["name"] = "Runecrafting"
    planner.import_text(json.dumps(data))
    check(
        "odd json: a skill with a different spelling is found by its position",
        "Imported 24" in planner.text("#import-message")
        and planner.current("runecraft") == SAMPLE_LEVELS["runecraft"],
        planner.text("#import-message"),
    )

    # Every name unrecognised, but the list still starts with Overall.
    planner.open_fresh()
    data = hiscores_data()
    for number, entry in enumerate(data["skills"]):
        if number > 0:
            entry["name"] = "Skill %d" % number
    planner.import_text(json.dumps(data))
    check(
        "odd json: with no names recognised, the order is used",
        "Imported 24" in planner.text("#import-message")
        and planner.current("strength") == SAMPLE_LEVELS["strength"],
        planner.text("#import-message"),
    )

    # Names unrecognised and no Overall entry: the order cannot be trusted.
    planner.open_fresh()
    data = hiscores_data()
    data["skills"] = data["skills"][1:]
    for number, entry in enumerate(data["skills"]):
        entry["name"] = "Skill %d" % number
    planner.import_text(json.dumps(data))
    check(
        "odd json: unrecognised names without an Overall entry are not guessed at",
        "Couldn't read" in planner.text("#import-message"),
        planner.text("#import-message"),
    )

    # A skill missing from the data is named in a warning.
    planner.open_fresh()
    data = hiscores_data()
    data["skills"] = [entry for entry in data["skills"] if entry["name"] != "Hunter"]
    planner.import_text(json.dumps(data))
    message = planner.text("#import-message")
    check(
        "odd json: a missing skill is named in the message",
        "Imported 23" in message and "Not found" in message and "Hunter" in message,
        message,
    )
    check(
        "odd json: the message about a missing skill is a warning",
        "warning" in planner.page.get_attribute("#import-message", "class"),
    )

    # A damaged entry in the list is skipped rather than crashing the import.
    planner.open_fresh()
    data = hiscores_data()
    data["skills"].insert(5, None)
    planner.import_text(json.dumps(data))
    check(
        "odd json: an empty entry in the list is skipped",
        "Imported" in planner.text("#import-message"),
        planner.text("#import-message"),
    )


def test_text_import_and_bad_input(planner):
    planner.open_fresh()

    planner.import_text(hiscores_text())
    check(
        "text import: total level is right",
        planner.text("#current-total") == "{:,}".format(SAMPLE_TOTAL + 24),
        planner.text("#current-total"),
    )

    planner.import_text("nonsense")
    check("bad import: shows an error", "Couldn't read" in planner.text("#import-message"))

    planner.import_text("")
    check(
        "empty import: asks for the hiscores",
        "Paste the hiscores" in planner.text("#import-message"),
    )


def test_xp_and_targets(planner):
    planner.open_fresh()
    planner.import_sample_stats()

    planner.set_target("fletching", 56)
    expected_xp = XP_FOR_LEVEL[56] - (XP_FOR_LEVEL[55] + EXTRA_XP)
    shown_xp = planner.text("tr[data-skill=fletching] .xp-needed")
    check(
        "xp: needed XP uses the real XP from the hiscores",
        shown_xp == "{:,}".format(expected_xp),
        shown_xp,
    )

    planner.click_step("fletching", -1)
    check("targets: the minus button lowers a target", planner.target("fletching") == 55)

    planner.set_target("fletching", 150)
    check("targets: a target above 99 becomes 99", planner.target("fletching") == 99)

    check("xp: level 99 needs 13,034,431 XP", XP_FOR_LEVEL[99] == 13034431)


def test_build_rules(planner):
    """The pure account setup: 75 Attack, 1 Defence, 63 Prayer, untrimmed Slayer cape."""
    planner.open_fresh()
    planner.import_sample_stats()
    planner.set_rule("attack", 75)
    planner.set_rule("defence", 1)
    planner.set_rule("prayer", 63)
    planner.toggle_untrimmed()

    check(
        "rules: highest total with the cape rule is 2198",
        "2198" in planner.text("#max-total-note"),
        planner.text("#max-total-note"),
    )
    check("rules: a world that is out of reach says so", "Max 2198" in planner.text("#worlds"))
    check(
        "rules: the summary lists the active rules",
        "Attack max 75" in planner.text("#rule-summary")
        and "untrimmed Slayer cape" in planner.text("#rule-summary"),
    )

    planner.max_targets()
    check(
        "rules: the max button reaches 2198",
        planner.text("#target-total") == "2,198",
        planner.text("#target-total"),
    )
    check(
        "rules: that build has combat level 88",
        planner.text("#target-combat") == "88",
        planner.text("#target-combat"),
    )
    check("rules: every check passes", "✗" not in planner.text("#rule-checks"))

    planner.toggle_untrimmed()  # off
    check(
        "rules: without the cape rule the highest total is 2218",
        "2218" in planner.text("#max-total-note"),
    )
    planner.max_targets()
    check(
        "rules: a full pure has combat level 89",
        planner.text("#target-combat") == "89",
        planner.text("#target-combat"),
    )

    planner.toggle_untrimmed()  # on again, with other skills already at 99
    check(
        "rules: other 99s trigger a warning or failure",
        "!" in planner.text("#rule-checks") or "✗" in planner.text("#rule-checks"),
    )

    planner.click_step("slayer", -1)
    check(
        "rules: 99s before the cape skill fail the check",
        "would trim the cape" in planner.text("#rule-checks"),
    )

    planner.click_step("attack", 1)
    check(
        "rules: a target over a cap is flagged",
        "✗ Attack target 76" in planner.text("#rule-checks")
        and "over-cap" in planner.page.get_attribute("tr[data-skill=attack]", "class"),
    )


def test_cheapest_route(planner):
    planner.open_fresh()
    planner.import_sample_stats()
    planner.toggle_untrimmed()  # every skill except Slayer is capped at 98

    # Set the combat targets by hand, then lock them so the route leaves them alone.
    for skill, level in {
        "attack": 75,
        "strength": 95,
        "hitpoints": 96,
        "ranged": 96,
        "magic": 95,
        "prayer": 63,
    }.items():
        planner.set_target(skill, level)
    planner.lock_combat()
    planner.toggle_lock("slayer")
    planner.set_target("slayer", 99)

    planner.click_world(2000)
    other_skills = [
        skill for skill in SAMPLE_LEVELS if skill not in COMBAT_SKILLS and skill != "slayer"
    ]

    check(
        "route: reaches exactly 2000",
        planner.text("#target-total") == "2,000",
        planner.text("#target-total"),
    )
    check(
        "route: leaves locked skills alone",
        planner.target("strength") == 95
        and planner.target("slayer") == 99
        and planner.target("defence") == 1,
    )
    check(
        "route: never goes below current levels",
        all(planner.target(skill) >= SAMPLE_LEVELS[skill] for skill in other_skills),
    )
    check("route: respects the 98 cap", all(planner.target(skill) <= 98 for skill in other_skills))

    levels = [planner.target(skill) for skill in other_skills]
    check("route: spreads levels evenly", max(levels) - min(levels) <= 2, str(levels))
    check("route: confirms success", "Targets set for the 2000" in planner.text("#route-message"))

    planner.click_world(1500)
    check(
        "route: a lower goal fills up to exactly 1500",
        planner.text("#target-total") == "1,500",
        planner.text("#target-total"),
    )
    planner.click_world(1500)
    check(
        "route: repeating the same route changes nothing", planner.text("#target-total") == "1,500"
    )


def test_impossible_route(planner):
    planner.open_fresh()
    planner.import_sample_stats()
    planner.toggle_untrimmed()

    planner.unlock_all()
    check("unlock all: clears every lock", not planner.is_locked("strength"))

    # Lock everything except Cooking, so only Cooking can move.
    planner.lock_everything_except("cooking")
    planner.reset_targets()
    planner.click_world(2000)

    check(
        "impossible route: explains why",
        "Can't reach 2000" in planner.text("#route-message"),
        planner.text("#route-message"),
    )
    check(
        "impossible route: only the unlocked skill moves",
        planner.target("cooking") == 98 and planner.target("fletching") == 55,
    )


def test_adding_and_removing_rules(planner):
    planner.open_fresh()
    planner.import_sample_stats()

    planner.page.select_option("#new-rule-skill", "strength")
    planner.page.click("#add-rule")
    check(
        "add rule: a second Strength rule appears",
        planner.text("#rules").count("Strength max") == 2,
    )
    check(
        "add rule: it starts at the current level",
        planner.value('#rules input[data-rule="7"][data-field=max]') == "37",
    )
    check(
        "add rule: only added rules can be removed",
        planner.page.locator("#rules button[data-field=remove]").count() == 1,
    )

    planner.page.click('#rules button[data-rule="7"]')
    check("remove rule: it disappears", planner.rule_count() == 8)  # 7 built-in + the cape rule

    planner.toggle_untrimmed()  # the rule has to be on to appear in the summary and caps
    planner.page.select_option("#rules select[data-field=untrimmed-skill]", "agility")
    check(
        "cape rule: the skill can be changed",
        "untrimmed Agility cape" in planner.text("#rule-summary"),
    )
    check(
        "cape rule: Slayer is now capped like the others",
        "Max 98" in planner.text("tr[data-skill=slayer] .cap-note"),
    )

    # Typing a silly level into a cap is corrected.
    planner.type_number(planner.rule_selector("attack", "max"), 500)
    check(
        "rule level: above 99 becomes 99",
        planner.value(planner.rule_selector("attack", "max")) == "99",
    )
    planner.type_number(planner.rule_selector("attack", "max"), 0)
    check(
        "rule level: below 1 becomes 1",
        planner.value(planner.rule_selector("attack", "max")) == "1",
    )

    # A rule fades when it is switched off.
    planner.page.click(planner.rule_selector("attack", "enabled"))
    planner.page.click(planner.rule_selector("attack", "enabled"))
    check(
        "rule row: fades when unchecked",
        "disabled" in planner.page.get_attribute("#rules .rule", "class"),
    )


def test_clicks_are_not_lost(planner):
    """Regression tests. Rebuilding part of the page while the user is
    clicking can swallow the click, so these pieces must stay the same
    elements when something else changes."""
    planner.open_fresh()
    planner.page.select_option("#new-rule-skill", "mining")
    planner.page.click("#add-rule")
    rules_before = planner.rule_count()

    # Type in one rule's number box, then click Remove on another rule straight away.
    planner.page.fill(planner.rule_selector("attack", "max"), "60")
    planner.page.click("#rules button[data-field=remove]")
    check(
        "click: Remove works right after editing another rule",
        planner.rule_count() == rules_before - 1,
    )

    # Mark a world button, then change something. If the mark survives, the button was not rebuilt.
    planner.page.evaluate("document.querySelector('.world button').dataset.mark = 'kept'")
    planner.set_target("attack", 10)
    check(
        "click: world buttons are not rebuilt when a target changes",
        planner.page.evaluate("document.querySelector('.world button').dataset.mark") == "kept",
    )

    planner.page.evaluate("document.querySelector('#rules .rule').dataset.mark = 'kept'")
    planner.page.click(planner.rule_selector("attack", "enabled"))
    check(
        "click: the rules list is not rebuilt when a rule changes",
        planner.page.evaluate("document.querySelector('#rules .rule').dataset.mark") == "kept",
    )


def test_editing_current_levels(planner):
    planner.open_fresh()
    planner.import_sample_stats()

    planner.set_current("sailing", 10)
    check("current level: can be typed in by hand", planner.current("sailing") == 10)

    planner.set_current("hitpoints", 3)
    check("current level: Hitpoints cannot go below 10", planner.current("hitpoints") == 10)


def test_hiscore_link(planner):
    planner.open_fresh()
    check("link: hidden until a username is typed", planner.page.is_hidden("#hiscore-link"))

    planner.page.fill("#username", "Some Name")
    planner.page.select_option("#hiscore-mode", "hiscore_oldschool_hardcore_ironman")
    link = planner.page.get_attribute("#hiscore-link", "href")
    expected = (
        "https://secure.runescape.com/m=hiscore_oldschool_hardcore_ironman"
        "/index_lite.json?player=Some%20Name"
    )
    check("link: built from the username and hiscore type", link == expected, link)


def test_saving(planner):
    planner.open_fresh()
    planner.import_sample_stats()
    planner.set_rule("attack", 75)
    planner.page.fill("#username", "Some Name")

    before = (
        planner.text("#current-total"),
        planner.text("#target-total"),
        planner.text("#rule-summary"),
    )
    planner.page.reload()
    after = (
        planner.text("#current-total"),
        planner.text("#target-total"),
        planner.text("#rule-summary"),
    )
    check("saving: everything survives a reload", before == after, "%s vs %s" % (before, after))
    check("saving: the username survives a reload", planner.value("#username") == "Some Name")


def test_partial_and_damaged_saves(planner):
    """Saved data can be incomplete or damaged. The page should keep what it
    can understand and quietly ignore the rest."""
    planner.open_fresh()

    # A save that only mentions some things. Everything it leaves out gets a default.
    planner.save_raw(
        json.dumps(
            {
                "current": {"attack": {"level": 60, "xp": 273742}},
                "target": {"attack": 70},
                "locked": {"attack": True},
                "username": "Someone",
                "hiscoreMode": "hiscore_oldschool_ironman",
                "rules": [{"skill": "attack", "max": 75, "enabled": True}],
                "untrimmed": {"skill": "slayer", "enabled": True},
            }
        )
    )
    check(
        "partial save: levels, targets and locks load",
        planner.current("attack") == 60
        and planner.target("attack") == 70
        and planner.is_locked("attack"),
    )
    check(
        "partial save: the username and account type load",
        planner.value("#username") == "Someone"
        and planner.value("#hiscore-mode") == "hiscore_oldschool_ironman",
    )
    check(
        "partial save: rules load",
        "Attack max 75" in planner.text("#rule-summary")
        and "untrimmed Slayer" in planner.text("#rule-summary"),
    )
    check(
        "partial save: the missing combat caps are filled in",
        planner.rule_count() == 8 and "Magic max" in planner.text("#rules"),
    )
    check(
        "partial save: skills it leaves out start at their minimum", planner.current("cooking") == 1
    )

    planner.save_raw("{broken")
    check("damaged save: falls back to a fresh start", planner.text("#current-total") == "33")

    # A save in a layout this version does not recognise is ignored, not misread.
    planner.save_raw(json.dumps({"cur": {"attack": {"level": 60, "xp": 273742}}, "rsn": "Old"}))
    check(
        "unrecognised save: starts fresh",
        planner.text("#current-total") == "33" and planner.value("#username") == "",
    )

    # A target that is not a number must not show up as an empty box.
    planner.save_raw(json.dumps({"current": {}, "target": {"attack": "abc"}}))
    check(
        "damaged save: a bad target falls back to the current level", planner.target("attack") == 1
    )

    # A rule for something that is not a skill is ignored.
    planner.save_raw(json.dumps({"rules": [{"skill": "constructor", "max": 5, "enabled": True}]}))
    check(
        "damaged save: a rule for an unknown skill is ignored",
        planner.rule_count() == 8 and "No build rules checked" in planner.text("#rule-summary"),
    )


def test_preference_check_boxes(planner):
    """The route preference check boxes: four of them, in two groups."""
    planner.open_fresh()

    boxes = planner.page.locator("#route-preferences input[type=checkbox]").count()
    check(
        "preferences: there are four check boxes, none ticked",
        boxes == 4 and planner.ticked_preferences() == [],
    )
    titles = planner.text("#route-preferences")
    check(
        "preferences: the two groups have titles",
        "How you want to train" in titles and "What you want to spend" in titles,
    )

    # Only one per group can be ticked at a time. Check boxes are listed in page order:
    # afk, active, no-supplies, buyable.
    planner.click_preference("afk")
    check("preferences: ticking one selects it", planner.ticked_preferences() == ["afk"])
    planner.click_preference("active")
    check(
        "preferences: ticking another in the same group unticks the first",
        planner.ticked_preferences() == ["active"],
    )
    planner.click_preference("no-supplies")
    check(
        "preferences: one from each group can be ticked together",
        planner.ticked_preferences() == ["active", "no-supplies"],
    )
    planner.click_preference("buyable")
    check(
        "preferences: switching in one group leaves the other group alone",
        planner.ticked_preferences() == ["active", "buyable"],
    )
    planner.click_preference("buyable")
    check(
        "preferences: unticking leaves that group empty", planner.ticked_preferences() == ["active"]
    )

    # The clicked check box must stay the same element, or a click could be lost.
    planner.page.evaluate(
        "document.querySelector('#route-preferences .rule').dataset.mark = 'kept'"
    )
    planner.click_preference("no-supplies")
    check(
        "preferences: the list is not rebuilt when one is ticked",
        planner.page.evaluate("document.querySelector('#route-preferences .rule').dataset.mark")
        == "kept",
    )

    # The header and the route message name every ticked preference.
    planner.open_fresh()
    planner.click_preference("afk")
    check(
        "preferences: the header mentions one choice",
        "favouring AFK skills" in planner.text("#rule-summary"),
    )
    planner.click_preference("buyable")
    planner.click_world(1500)
    check(
        "preferences: the header mentions both choices",
        "favouring AFK skills and skills you can buy" in planner.text("#rule-summary"),
        planner.text("#rule-summary"),
    )
    check(
        "preferences: the route message mentions both choices",
        "favouring AFK skills and skills you can buy" in planner.text("#route-message"),
        planner.text("#route-message"),
    )


def test_preference_ratings_table(planner):
    """route-preferences.js is edited by hand, so check it for slips."""
    planner.open_fresh()
    tables = planner.rating_tables()

    check(
        "ratings table: it only names real skills",
        all(skill in SAMPLE_LEVELS for table in tables.values() for skill in table),
    )
    missing = {name: sorted(set(SAMPLE_LEVELS) - set(table)) for name, table in tables.items()}
    check(
        "ratings table: every preference rates all 24 skills",
        all(not skills for skills in missing.values()),
        str({n: s for n, s in missing.items() if s}),
    )
    check(
        "ratings table: ratings are 0 to 3 (or bands of them with start levels 1 to 99)",
        all(rating_is_valid(rating) for table in tables.values() for rating in table.values()),
    )

    details = planner.page.evaluate("ROUTE_PREFERENCES.map(p => [p.id, p.group, p.summary])")
    groups = planner.page.evaluate("PREFERENCE_GROUPS.map(g => g.id)")
    check(
        "ratings table: every preference has a known group and a summary",
        all(group in groups and summary for _, group, summary in details),
        str(details),
    )
    check(
        "ratings table: every group has at least two preferences to choose between",
        all(sum(1 for _, group, _ in details if group == g) >= 2 for g in groups),
    )


def test_preference_routes(planner):
    """What the preferences do to a route."""
    planner.open_fresh()
    tables = planner.rating_tables()

    # Without a preference, a route spreads levels evenly.
    planner.click_world(1500)
    levels = list(planner.all_targets().values())
    check(
        "route without a preference: levels are even", max(levels) - min(levels) <= 2, str(levels)
    )

    # With each preference the goal is still met exactly. Preferences that give each skill
    # one rating also push rated skills higher by a predictable amount.
    for preference_id, table in tables.items():
        planner.open_fresh()
        planner.click_preference(preference_id)
        planner.click_world(1500)
        check(
            "%s: the route still reaches exactly 1500" % preference_id,
            planner.text("#target-total") == "1,500",
            planner.text("#target-total"),
        )

        # Group the skills by rating. Skills whose rating changes with level are left out,
        # because their rating depends on where they end up. test_level_based_ratings
        # checks those.
        targets = planner.all_targets()
        by_rating = {}
        for skill in SAMPLE_LEVELS:
            # The app treats a missing skill as 0. test_preference_ratings_table reports it.
            rating = table.get(skill, 0)
            if not isinstance(rating, dict):
                by_rating.setdefault(rating, []).append(targets[skill])
        averages = {rating: average(levels) for rating, levels in by_rating.items()}
        if len(averages) < 2:
            continue  # nothing to compare

        # The highest-rated skills should end up well above the lowest-rated ones. This does
        # not assume that any particular rating (such as 3) is used.
        highest, lowest = max(averages), min(averages)
        check(
            "%s: higher-rated skills end up at least 5 levels higher per rating point"
            % preference_id,
            averages[highest] - averages[lowest] >= 5 * (highest - lowest),
            str(averages),
        )
        # Each rating point should be worth about 7 levels (see route-preferences.js).
        steps = [averages[r + 1] - averages[r] for r in averages if r + 1 in averages]
        check(
            "%s: each rating point is worth 5 to 10 levels" % preference_id,
            all(5 <= step <= 10 for step in steps),
            str(steps),
        )

    # Caps and locks still win over a preference.
    planner.open_fresh()
    planner.toggle_untrimmed()
    planner.click_preference("afk")
    planner.set_target("strength", 50)
    planner.toggle_lock("strength")
    planner.click_world(2000)
    targets = planner.all_targets()
    check("preferences: a locked skill keeps its target", targets["strength"] == 50)
    check(
        "preferences: the 98 cap still holds",
        all(level <= 98 for skill, level in targets.items() if skill != "slayer"),
    )


def test_combined_preferences(planner):
    """With one preference from each group ticked, a skill counts as its weaker rating."""
    planner.open_fresh()
    tables = planner.rating_tables()

    planner.click_preference("afk")
    planner.click_preference("no-supplies")
    planner.click_world(1500)
    check(
        "combined: the route still reaches exactly 1500",
        planner.text("#target-total") == "1,500",
        planner.text("#target-total"),
    )

    # Group the skills by their weaker rating (skills with bands are left out).
    targets = planner.all_targets()
    by_weaker = {}
    for skill in SAMPLE_LEVELS:
        afk, supplies = tables["afk"][skill], tables["no-supplies"][skill]
        if not isinstance(afk, dict) and not isinstance(supplies, dict):
            by_weaker.setdefault(min(afk, supplies), []).append(targets[skill])
    averages = {rating: average(levels) for rating, levels in by_weaker.items()}

    highest, lowest = max(averages), min(averages)
    check(
        "combined: skills with a higher weaker rating end up at least 5 levels higher per point",
        averages[highest] - averages[lowest] >= 5 * (highest - lowest),
        str(averages),
    )
    in_order = [averages[rating] for rating in sorted(averages)]
    check(
        "combined: levels do not fall as the weaker rating rises",
        all(low <= high + 1 for low, high in zip(in_order, in_order[1:])),
        str(averages),
    )

    # Ticking two must not tilt harder than ticking one.
    spread_two = averages[highest] - averages[lowest]
    planner.open_fresh()
    planner.click_preference("afk")
    planner.click_world(1500)
    single = planner.all_targets()
    afk_by_rating = {}
    for skill in SAMPLE_LEVELS:
        if not isinstance(tables["afk"][skill], dict):
            afk_by_rating.setdefault(tables["afk"][skill], []).append(single[skill])
    afk_averages = {rating: average(levels) for rating, levels in afk_by_rating.items()}
    spread_one = afk_averages[max(afk_averages)] - afk_averages[min(afk_averages)]
    check(
        "combined: two preferences do not tilt harder than one",
        spread_two <= spread_one + 2,
        "two: %.1f, one: %.1f" % (spread_two, spread_one),
    )


def test_combining_uses_the_weaker_rating(planner):
    """A skill is only favoured if both ticked preferences favour it. This uses made-up ratings,
    so it keeps working however the real ratings are edited."""
    planner.open_fresh()
    planner.page.evaluate("""() => {
            const afk = ROUTE_PREFERENCES.find(p => p.id === 'afk').ratings;
            const supplies = ROUTE_PREFERENCES.find(p => p.id === 'no-supplies').ratings;
            afk.runecraft = 0; supplies.runecraft = 3;   // liked by one preference only
            afk.cooking = 3;   supplies.cooking = 0;     // liked by the other one only
            afk.mining = 3;    supplies.mining = 3;      // liked by both
            afk.fishing = 2;   supplies.fishing = 3;     // liked by both, one more than the other
        }""")

    def factor(skill):
        return planner.page.evaluate("([skill]) => routeCostFactor(skill, 50)", [skill])

    check("weaker rating: with nothing ticked every skill costs the same", factor("mining") == 1)

    planner.click_preference("no-supplies")
    check("weaker rating: one preference alone favours its skills", factor("runecraft") == 0.125)

    planner.click_preference("afk")
    check(
        "weaker rating: a skill liked by only one preference is not favoured",
        factor("runecraft") == 1 and factor("cooking") == 1,
        "%s, %s" % (factor("runecraft"), factor("cooking")),
    )
    check("weaker rating: a skill liked by both is fully favoured", factor("mining") == 0.125)
    check("weaker rating: otherwise the weaker rating counts", factor("fishing") == 0.25)


def test_real_hiscores_shape(planner):
    """The JSON page the real hiscores send: extra fields, a skill with rank -1 but level 1 and
    0 XP, and a long list of activities. (The numbers are made up.)"""
    planner.open_fresh()
    data = hiscores_data()
    data["name"] = "Example"
    for entry in data["skills"]:
        if entry["name"] in ("Defence", "Sailing"):
            entry.update({"rank": -1, "level": 1, "xp": 0})
    data["activities"] = [
        {"id": 0, "name": "Grid Points", "rank": -1, "score": 0},
        {"id": 7, "name": "Clue Scrolls (all)", "rank": 17971, "score": 104},
        {"id": 87, "name": "Wintertodt", "rank": 104447, "score": 112},
    ]
    planner.import_text(json.dumps(data))
    check(
        "real shape: all 24 skills are imported",
        "Imported 24 skills." in planner.text("#import-message"),
        planner.text("#import-message"),
    )
    check(
        "real shape: the total matches the Overall level on the page",
        planner.text("#current-total") == "{:,}".format(SAMPLE_TOTAL),
        planner.text("#current-total"),
    )
    check("real shape: an unranked skill keeps its level", planner.current("defence") == 1)


def test_preference_saving(planner):
    """The chosen preferences are remembered, and nonsense in a save is ignored."""
    planner.open_fresh()
    planner.click_preference("afk")
    planner.click_preference("buyable")
    planner.page.reload()
    check(
        "preferences: both choices survive a reload",
        planner.ticked_preferences() == ["afk", "buyable"],
    )

    # Earlier versions saved a single preference as text. It goes into its own group.
    planner.save_raw(json.dumps({"routePreference": "no-supplies"}))
    check(
        "preferences: an earlier single-text save is understood",
        planner.ticked_preferences() == ["no-supplies"],
    )
    planner.save_raw(json.dumps({"routePreference": "afk"}))
    check(
        "preferences: an earlier single-text save for another group is understood",
        planner.ticked_preferences() == ["afk"],
    )

    # Anything that does not make sense is ignored.
    bad_saves = {
        "an unknown name": {"routePreferences": {"activity": "nonsense", "resources": "nonsense"}},
        "a choice under the wrong group": {
            "routePreferences": {"activity": "buyable", "resources": "afk"}
        },
        "choices that are not text": {"routePreferences": {"activity": 5, "resources": ["afk"]}},
        "choices that are not an object": {"routePreferences": "afk"},
        "an earlier save that is not text": {"routePreference": 5},
        "an earlier save with an unknown name": {"routePreference": "nonsense"},
    }
    for description, saved in bad_saves.items():
        planner.save_raw(json.dumps(saved))
        check(
            "preferences: a save with %s is ignored" % description,
            planner.ticked_preferences() == [],
            str(planner.ticked_preferences()),
        )


def test_level_based_ratings(planner):
    """Ratings can depend on level, such as Runecraft only being AFK from 77."""
    planner.open_fresh()

    # Looking up a rating by level.
    lookups = planner.page.evaluate("""() => [
        ratingAtLevel({1: 0, 77: 2}, 76),
        ratingAtLevel({1: 0, 77: 2}, 77),
        ratingAtLevel({1: 0, 77: 2}, 99),
        ratingAtLevel({10: 2}, 5),
        ratingAtLevel(3, 50),
        ratingAtLevel(undefined, 50),
        ratingAtLevel({1: 0, 45: 1, 60: 2, 75: 3}, 74),
    ]""")
    check(
        "bands: a rating starts at its level, not before", lookups[:4] == [0, 2, 2, 0], str(lookups)
    )
    check("bands: a plain number applies at every level", lookups[4] == 3)
    check("bands: a missing rating counts as 0", lookups[5] == 0)
    check("bands: the latest band that has started is used", lookups[6] == 2, str(lookups))

    # The two points made about the AFK table.
    afk = planner.ratings_by_level()["afk"]
    check("AFK: Runecraft is not AFK below level 77", rating_at(afk, "runecraft", 76) == 0)
    check("AFK: Runecraft is AFK from level 77", rating_at(afk, "runecraft", 77) > 0)
    check(
        "AFK: Agility is rated 0 at every level",
        all(rating == 0 for rating in afk["agility"]),
        str(afk["agility"]),
    )

    # What that does to a route. Compare with the route that has no preference.
    def route(world, preference_id):
        planner.open_fresh()
        if preference_id:
            planner.click_preference(preference_id)
        planner.click_world(world)
        return planner.all_targets()

    plain = route(1500, None)
    afk_low = route(1500, "afk")
    check(
        "AFK route: Agility ends well below where it would with no preference",
        afk_low["agility"] <= min(plain.values()) - 8,
        "%s vs %s" % (afk_low["agility"], min(plain.values())),
    )
    check(
        "AFK route: Runecraft is treated like an unfavoured skill while it is below 77",
        afk_low["runecraft"] < 77 and abs(afk_low["runecraft"] - afk_low["agility"]) <= 2,
        "runecraft %s, agility %s" % (afk_low["runecraft"], afk_low["agility"]),
    )

    afk_early = route(1250, "afk")
    check(
        "AFK route: Woodcutting waits for level 45 before it is favoured",
        afk_early["woodcutting"] < 45,
        str(afk_early["woodcutting"]),
    )

    afk_high = route(2200, "afk")
    check(
        "AFK route: once past 77, Runecraft is favoured over Agility",
        afk_high["runecraft"] >= afk_high["agility"] + 5,
        "runecraft %s, agility %s" % (afk_high["runecraft"], afk_high["agility"]),
    )


def test_afk_ratings_match_the_wiki_data(planner):
    """The AFK ratings must be exactly what docs/afk-ratings.md says the wiki's methods give.
    Ratings set by hand are only allowed if they are listed in docs/afk-overrides.csv."""
    planner.open_fresh()
    methods = read_csv("afk-methods.csv")
    overrides = read_overrides()
    page_ratings = planner.ratings_by_level()["afk"]

    check(
        "methods file: every row names a known skill or group",
        all(
            skill in SAMPLE_LEVELS or skill in COMBAT_GROUPS
            for method in methods
            for skill in [method["applies_to"]]
        ),
    )
    check(
        "methods file: every row is from a known table",
        all(method["section"] in ("skilling", "combat", "recurring") for method in methods),
    )
    # Count each method once. Second rows and extra-XP rows do not add to the page's counts.
    found = {}
    for method in methods:
        if not method["method"].startswith("Extra XP"):
            found.setdefault(method["section"], set()).add((method["applies_to"], method["method"]))
    counts = {section: len(names) for section, names in found.items()}
    check(
        "methods file: it has the page's 73 skilling, 13 combat and 4 recurring methods",
        counts == {"skilling": 73, "combat": 13, "recurring": 4},
        str(counts),
    )
    check(
        "overrides file: it names real skills, with start levels 1 to 99 and ratings 0 to 3",
        all(
            skill in SAMPLE_LEVELS and 1 <= from_level <= 99 and rating in (0, 1, 2, 3)
            for skill, bands in overrides.items()
            for from_level, rating in bands
        ),
    )

    differences = []
    for skill in SAMPLE_LEVELS:
        for level in range(1, 100):
            override = override_rating_at(overrides.get(skill, []), level)
            if override is not None:
                expected, source = override, "override"
            else:
                expected, source = derive_afk_rating(methods, skill, level), "wiki data"
            shown = rating_at(page_ratings, skill, level)
            if shown != expected:
                differences.append(
                    "%s at level %d: route-preferences.js says %s, %s says %s"
                    % (skill, level, shown, source, expected)
                )
                break  # one example per skill is enough
    check(
        "AFK ratings: every skill matches the wiki data or a listed override",
        not differences,
        "; ".join(differences),
    )


def test_readme_feature_map(planner):
    """Everything the README's "Where to find each feature" table names must exist."""
    planner.open_fresh()
    readme = (PROJECT_FOLDER / "README.md").read_text(encoding="utf-8")
    table = readme.split("## Where to find each feature")[1].split("\n## ")[0]
    names = sorted(set(re.findall(r"`([A-Za-z][A-Za-z0-9_]*)`", table)))

    missing = [
        name
        for name in names
        if planner.page.evaluate("name => eval('typeof ' + name)", name) == "undefined"
    ]
    check(
        "README feature map: it names at least 10 things in script.js", len(names) >= 10, str(names)
    )
    check("README feature map: everything it names exists", not missing, str(missing))


def test_status_messages_do_not_go_stale(planner):
    """A message about what the last route or import did must disappear once it is no
    longer true."""
    planner.open_fresh()
    planner.click_preference("afk")
    planner.click_world(1500)
    check(
        "messages: a route shows what it did",
        "Targets set for the 1500 world, favouring AFK skills" in planner.text("#route-message"),
        planner.text("#route-message"),
    )
    planner.click_preference("afk")
    check(
        "messages: unticking a preference clears the route message",
        planner.text("#route-message") == "",
        planner.text("#route-message"),
    )

    planner.click_world(1500)
    planner.click_step("attack", 1)
    check(
        "messages: changing a target clears the route message",
        planner.text("#route-message") == "",
        planner.text("#route-message"),
    )

    planner.import_text(hiscores_json())
    check("messages: an import shows what it did", "Imported 24" in planner.text("#import-message"))
    planner.set_current("sailing", 10)
    check(
        "messages: changing a level clears the import message",
        planner.text("#import-message") == "",
        planner.text("#import-message"),
    )


def test_mobile_layout(browser, page_url):
    phone = browser.new_context(viewport={"width": 375, "height": 800}).new_page()
    phone.goto(page_url)
    phone.wait_for_timeout(900)  # let the fade-in finish

    width = phone.evaluate("document.documentElement.scrollWidth")
    check("mobile: the page does not scroll sideways", width <= 375, str(width))

    # The last world label sits at the far right of the bar, so make sure it is not cut off.
    label_right = phone.evaluate(
        "[...document.querySelectorAll('.track-gate span')].pop().getBoundingClientRect().right"
    )
    panel_right = phone.evaluate(
        "document.querySelector('.track').closest('.panel').getBoundingClientRect().right"
    )
    check(
        "mobile: the last world label stays inside its panel",
        label_right <= panel_right,
        "%s > %s" % (label_right, panel_right),
    )
    phone.close()


# =============================================================================
# 4. RUN EVERYTHING
# =============================================================================


def main():
    page_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PAGE
    page_url = page_path.as_uri()
    print("Testing %s\n" % page_path)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_context(viewport={"width": 1100, "height": 1200}).new_page()

        # Collect anything that goes wrong in the background while the tests run.
        errors = []
        outside_requests = []

        def note_page_error(error):
            errors.append(str(error))

        def note_console_message(message):
            if message.type == "error":
                errors.append(message.text)

        def note_request(request):
            if not request.url.startswith("file:"):
                outside_requests.append(request.url)

        page.on("pageerror", note_page_error)
        page.on("console", note_console_message)
        page.on("request", note_request)

        planner = Planner(page, page_url)
        for test_group in [
            test_fresh_page,
            test_json_import,
            test_json_import_with_odd_data,
            test_real_hiscores_shape,
            test_text_import_and_bad_input,
            test_xp_and_targets,
            test_build_rules,
            test_cheapest_route,
            test_impossible_route,
            test_adding_and_removing_rules,
            test_clicks_are_not_lost,
            test_editing_current_levels,
            test_hiscore_link,
            test_saving,
            test_partial_and_damaged_saves,
            test_preference_check_boxes,
            test_preference_ratings_table,
            test_preference_routes,
            test_combined_preferences,
            test_combining_uses_the_weaker_rating,
            test_preference_saving,
            test_level_based_ratings,
            test_afk_ratings_match_the_wiki_data,
            test_status_messages_do_not_go_stale,
            test_readme_feature_map,
        ]:
            run_group(test_group, planner)
        run_group(test_mobile_layout, browser, page_url)

        check("no errors appeared in the browser console", not errors, "; ".join(errors))
        check(
            "the page makes no network requests", not outside_requests, "; ".join(outside_requests)
        )
        browser.close()

    for name, passed, detail in results:
        print(("PASS  " if passed else "FAIL  ") + name + ("" if passed else "   [%s]" % detail))

    passed_count = sum(1 for _, passed, _ in results if passed)
    print("\n%d/%d passed" % (passed_count, len(results)))
    sys.exit(0 if passed_count == len(results) else 1)


if __name__ == "__main__":
    main()
