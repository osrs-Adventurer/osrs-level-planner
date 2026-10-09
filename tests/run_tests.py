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

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


# =============================================================================
# 1. SETTINGS AND SAMPLE DATA
# =============================================================================

# By default, test the index.html that sits one folder above this file.
DEFAULT_PAGE = Path(__file__).resolve().parent.parent / "index.html"

# The name the page saves its data under in the browser (see STORAGE_KEY in script.js).
STORAGE_KEY = "osrs-level-planner-v1"

# A made-up account, listed in the same order as the hiscores.
SAMPLE_LEVELS = {
    "attack": 60, "defence": 1, "strength": 37, "hitpoints": 35, "ranged": 48,
    "prayer": 43, "magic": 49, "cooking": 70, "woodcutting": 60, "fletching": 55,
    "fishing": 62, "firemaking": 50, "crafting": 45, "smithing": 70, "mining": 60,
    "herblore": 40, "agility": 50, "thieving": 55, "slayer": 44, "farming": 45,
    "runecraft": 40, "hunter": 50, "construction": 40, "sailing": 1,
}
SAMPLE_TOTAL = sum(SAMPLE_LEVELS.values())

COMBAT_SKILLS = ["attack", "defence", "strength", "hitpoints", "ranged", "prayer", "magic"]

# The order the built-in level caps appear in the "Build rules" section.
RULE_ORDER = ["attack", "strength", "defence", "hitpoints", "ranged", "magic", "prayer"]


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


def hiscores_json():
    """The sample account, written the way the JSON hiscores look.
    Sailing is left unranked (-1), as it is for players who have never trained it."""
    skills = [{"id": 0, "name": "Overall", "rank": 1, "level": SAMPLE_TOTAL, "xp": 1}]
    for number, (skill, level) in enumerate(SAMPLE_LEVELS.items(), start=1):
        skills.append({
            "id": number,
            "name": skill.capitalize(),
            "rank": 5,
            "level": level,
            "xp": XP_FOR_LEVEL[level] + EXTRA_XP,
        })
    skills[-1]["level"] = -1
    skills[-1]["xp"] = -1
    return json.dumps({"skills": skills, "activities": []})


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

results = []   # one (name, passed, detail) entry per check


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
        "#rules input[data-field=max]", "inputs => inputs.map(input => input.value)")
    check("fresh: seven combat caps start at the skill minimum",
          caps == ["1", "1", "1", "10", "1", "1", "1"], str(caps))

    rule_text = planner.text("#rules")
    check("fresh: combat caps are listed in order",
          all(name + " max" in rule_text for name in
              ["Attack", "Strength", "Defence", "Hitpoints", "Ranged", "Magic", "Prayer"]))
    check("fresh: built-in caps cannot be removed",
          planner.page.locator("#rules button[data-field=remove]").count() == 0)
    check("fresh: highest possible total is 2376", "2376" in planner.text("#max-total-note"),
          planner.text("#max-total-note"))
    check("fresh: there is one card per world", planner.page.locator(".world").count() == 8)

    # If style.css failed to load, the page would have a white background.
    background = planner.page.evaluate("getComputedStyle(document.body).backgroundColor")
    check("fresh: style.css is loaded", background == "rgb(15, 10, 10)", background)


def test_json_import(planner):
    planner.open_fresh()
    planner.import_text(hiscores_json())

    check("json import: reports 24 skills", "Imported 24" in planner.text("#import-message"),
          planner.text("#import-message"))
    check("json import: total level is right",
          planner.text("#current-total") == "{:,}".format(SAMPLE_TOTAL), planner.text("#current-total"))
    check("json import: an unranked skill becomes level 1", planner.current("sailing") == 1)
    # base 0.25 x (1 + 35 + 21) = 14.25, melee 0.325 x (60 + 37) = 31.525, total 45.77
    check("json import: combat level is 45", planner.text("#current-combat") == "45",
          planner.text("#current-combat"))
    check("json import: targets are never below current levels",
          all(planner.target(skill) >= level for skill, level in SAMPLE_LEVELS.items()))


def test_text_import_and_bad_input(planner):
    planner.open_fresh()

    planner.import_text(hiscores_text())
    check("text import: total level is right",
          planner.text("#current-total") == "{:,}".format(SAMPLE_TOTAL + 24), planner.text("#current-total"))

    planner.import_text("nonsense")
    check("bad import: shows an error", "Couldn't read" in planner.text("#import-message"))

    planner.import_text("")
    check("empty import: asks for the hiscores", "Paste the hiscores" in planner.text("#import-message"))


def test_xp_and_targets(planner):
    planner.open_fresh()
    planner.import_sample_stats()

    planner.set_target("fletching", 56)
    expected_xp = XP_FOR_LEVEL[56] - (XP_FOR_LEVEL[55] + EXTRA_XP)
    shown_xp = planner.text("tr[data-skill=fletching] .xp-needed")
    check("xp: needed XP uses the real XP from the hiscores", shown_xp == "{:,}".format(expected_xp), shown_xp)

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

    check("rules: highest total with the cape rule is 2198", "2198" in planner.text("#max-total-note"),
          planner.text("#max-total-note"))
    check("rules: a world that is out of reach says so", "Max 2198" in planner.text("#worlds"))
    check("rules: the summary lists the active rules",
          "Attack max 75" in planner.text("#rule-summary")
          and "untrimmed Slayer cape" in planner.text("#rule-summary"))

    planner.max_targets()
    check("rules: the max button reaches 2198", planner.text("#target-total") == "2,198", planner.text("#target-total"))
    check("rules: that build has combat level 88", planner.text("#target-combat") == "88", planner.text("#target-combat"))
    check("rules: every check passes", "✗" not in planner.text("#rule-checks"))

    planner.toggle_untrimmed()   # off
    check("rules: without the cape rule the highest total is 2218", "2218" in planner.text("#max-total-note"))
    planner.max_targets()
    check("rules: a full pure has combat level 89", planner.text("#target-combat") == "89", planner.text("#target-combat"))

    planner.toggle_untrimmed()   # on again, with other skills already at 99
    check("rules: other 99s trigger a warning or failure",
          "!" in planner.text("#rule-checks") or "✗" in planner.text("#rule-checks"))

    planner.click_step("slayer", -1)
    check("rules: 99s before the cape skill fail the check", "would trim the cape" in planner.text("#rule-checks"))

    planner.click_step("attack", 1)
    check("rules: a target over a cap is flagged",
          "✗ Attack target 76" in planner.text("#rule-checks")
          and "over-cap" in planner.page.get_attribute("tr[data-skill=attack]", "class"))


def test_cheapest_route(planner):
    planner.open_fresh()
    planner.import_sample_stats()
    planner.toggle_untrimmed()   # every skill except Slayer is capped at 98

    # Set the combat targets by hand, then lock them so the route leaves them alone.
    for skill, level in {"attack": 75, "strength": 95, "hitpoints": 96,
                         "ranged": 96, "magic": 95, "prayer": 63}.items():
        planner.set_target(skill, level)
    planner.lock_combat()
    planner.toggle_lock("slayer")
    planner.set_target("slayer", 99)

    planner.click_world(2000)
    other_skills = [skill for skill in SAMPLE_LEVELS if skill not in COMBAT_SKILLS and skill != "slayer"]

    check("route: reaches exactly 2000", planner.text("#target-total") == "2,000", planner.text("#target-total"))
    check("route: leaves locked skills alone",
          planner.target("strength") == 95 and planner.target("slayer") == 99 and planner.target("defence") == 1)
    check("route: never goes below current levels",
          all(planner.target(skill) >= SAMPLE_LEVELS[skill] for skill in other_skills))
    check("route: respects the 98 cap", all(planner.target(skill) <= 98 for skill in other_skills))

    levels = [planner.target(skill) for skill in other_skills]
    check("route: spreads levels evenly", max(levels) - min(levels) <= 2, str(levels))
    check("route: confirms success", "Targets set for the 2000" in planner.text("#route-message"))

    planner.click_world(1500)
    check("route: a lower goal fills up to exactly 1500", planner.text("#target-total") == "1,500",
          planner.text("#target-total"))
    planner.click_world(1500)
    check("route: repeating the same route changes nothing", planner.text("#target-total") == "1,500")


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

    check("impossible route: explains why", "Can't reach 2000" in planner.text("#route-message"),
          planner.text("#route-message"))
    check("impossible route: only the unlocked skill moves",
          planner.target("cooking") == 98 and planner.target("fletching") == 55)


def test_adding_and_removing_rules(planner):
    planner.open_fresh()
    planner.import_sample_stats()

    planner.page.select_option("#new-rule-skill", "strength")
    planner.page.click("#add-rule")
    check("add rule: a second Strength rule appears", planner.text("#rules").count("Strength max") == 2)
    check("add rule: it starts at the current level",
          planner.value('#rules input[data-rule="7"][data-field=max]') == "37")
    check("add rule: only added rules can be removed",
          planner.page.locator("#rules button[data-field=remove]").count() == 1)

    planner.page.click('#rules button[data-rule="7"]')
    check("remove rule: it disappears", planner.rule_count() == 8)   # 7 built-in + the cape rule

    planner.toggle_untrimmed()   # the rule has to be on to appear in the summary and caps
    planner.page.select_option("#rules select[data-field=untrimmed-skill]", "agility")
    check("cape rule: the skill can be changed", "untrimmed Agility cape" in planner.text("#rule-summary"))
    check("cape rule: Slayer is now capped like the others",
          "Max 98" in planner.text("tr[data-skill=slayer] .cap-note"))

    # Typing a silly level into a cap is corrected.
    planner.type_number(planner.rule_selector("attack", "max"), 500)
    check("rule level: above 99 becomes 99", planner.value(planner.rule_selector("attack", "max")) == "99")
    planner.type_number(planner.rule_selector("attack", "max"), 0)
    check("rule level: below 1 becomes 1", planner.value(planner.rule_selector("attack", "max")) == "1")

    # A rule fades when it is switched off.
    planner.page.click(planner.rule_selector("attack", "enabled"))
    planner.page.click(planner.rule_selector("attack", "enabled"))
    check("rule row: fades when unchecked",
          "disabled" in planner.page.get_attribute("#rules .rule", "class"))


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
    check("click: Remove works right after editing another rule", planner.rule_count() == rules_before - 1)

    # Mark a world button, then change something. If the mark survives, the button was not rebuilt.
    planner.page.evaluate("document.querySelector('.world button').dataset.mark = 'kept'")
    planner.set_target("attack", 10)
    check("click: world buttons are not rebuilt when a target changes",
          planner.page.evaluate("document.querySelector('.world button').dataset.mark") == "kept")

    planner.page.evaluate("document.querySelector('#rules .rule').dataset.mark = 'kept'")
    planner.page.click(planner.rule_selector("attack", "enabled"))
    check("click: the rules list is not rebuilt when a rule changes",
          planner.page.evaluate("document.querySelector('#rules .rule').dataset.mark") == "kept")


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
    expected = "https://secure.runescape.com/m=hiscore_oldschool_hardcore_ironman/index_lite.json?player=Some%20Name"
    check("link: built from the username and hiscore type", link == expected, link)


def test_saving(planner):
    planner.open_fresh()
    planner.import_sample_stats()
    planner.set_rule("attack", 75)
    planner.page.fill("#username", "Some Name")

    before = (planner.text("#current-total"), planner.text("#target-total"), planner.text("#rule-summary"))
    planner.page.reload()
    after = (planner.text("#current-total"), planner.text("#target-total"), planner.text("#rule-summary"))
    check("saving: everything survives a reload", before == after, "%s vs %s" % (before, after))
    check("saving: the username survives a reload", planner.value("#username") == "Some Name")


def test_partial_and_damaged_saves(planner):
    """Saved data can be incomplete or damaged. The page should keep what it
    can understand and quietly ignore the rest."""
    planner.open_fresh()

    # A save that only mentions some things. Everything it leaves out gets a default.
    planner.save_raw(json.dumps({
        "current": {"attack": {"level": 60, "xp": 273742}},
        "target": {"attack": 70},
        "locked": {"attack": True},
        "username": "Someone",
        "hiscoreMode": "hiscore_oldschool_ironman",
        "rules": [{"skill": "attack", "max": 75, "enabled": True}],
        "untrimmed": {"skill": "slayer", "enabled": True},
    }))
    check("partial save: levels, targets and locks load",
          planner.current("attack") == 60 and planner.target("attack") == 70 and planner.is_locked("attack"))
    check("partial save: the username and account type load",
          planner.value("#username") == "Someone"
          and planner.value("#hiscore-mode") == "hiscore_oldschool_ironman")
    check("partial save: rules load",
          "Attack max 75" in planner.text("#rule-summary") and "untrimmed Slayer" in planner.text("#rule-summary"))
    check("partial save: the missing combat caps are filled in",
          planner.rule_count() == 8 and "Magic max" in planner.text("#rules"))
    check("partial save: skills it leaves out start at their minimum", planner.current("cooking") == 1)

    planner.save_raw("{broken")
    check("damaged save: falls back to a fresh start", planner.text("#current-total") == "33")

    # A save in a layout this version does not recognise is ignored, not misread.
    planner.save_raw(json.dumps({"cur": {"attack": {"level": 60, "xp": 273742}}, "rsn": "Old"}))
    check("unrecognised save: starts fresh", planner.text("#current-total") == "33" and planner.value("#username") == "")

    # A target that is not a number must not show up as an empty box.
    planner.save_raw(json.dumps({"current": {}, "target": {"attack": "abc"}}))
    check("damaged save: a bad target falls back to the current level", planner.target("attack") == 1)

    # A rule for something that is not a skill is ignored.
    planner.save_raw(json.dumps({"rules": [{"skill": "constructor", "max": 5, "enabled": True}]}))
    check("damaged save: a rule for an unknown skill is ignored",
          planner.rule_count() == 8 and "No build rules checked" in planner.text("#rule-summary"))


def test_mobile_layout(browser, page_url):
    phone = browser.new_context(viewport={"width": 375, "height": 800}).new_page()
    phone.goto(page_url)
    phone.wait_for_timeout(900)   # let the fade-in finish

    width = phone.evaluate("document.documentElement.scrollWidth")
    check("mobile: the page does not scroll sideways", width <= 375, str(width))

    # The last world label sits at the far right of the bar, so make sure it is not cut off.
    label_right = phone.evaluate(
        "[...document.querySelectorAll('.track-gate span')].pop().getBoundingClientRect().right")
    panel_right = phone.evaluate("document.querySelector('.track').closest('.panel').getBoundingClientRect().right")
    check("mobile: the last world label stays inside its panel", label_right <= panel_right,
          "%s > %s" % (label_right, panel_right))
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
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: outside_requests.append(request.url)
                if not request.url.startswith("file:") else None)

        planner = Planner(page, page_url)
        for test_group in [
            test_fresh_page,
            test_json_import,
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
        ]:
            run_group(test_group, planner)
        run_group(test_mobile_layout, browser, page_url)

        check("no errors appeared in the browser console", not errors, "; ".join(errors))
        check("the page makes no network requests", not outside_requests, "; ".join(outside_requests))
        browser.close()

    for name, passed, detail in results:
        print(("PASS  " if passed else "FAIL  ") + name + ("" if passed else "   [%s]" % detail))

    passed_count = sum(1 for _, passed, _ in results if passed)
    print("\n%d/%d passed" % (passed_count, len(results)))
    sys.exit(0 if passed_count == len(results) else 1)


if __name__ == "__main__":
    main()
