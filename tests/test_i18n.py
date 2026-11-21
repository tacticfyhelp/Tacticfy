"""Unit tests for the English / Hebrew UI translation tables served to the browser."""

import re
import unittest

from src import i18n
from src.engine.bench_optimizer import SCENARIO_MINUTES
from src.engine.training_advisor import GOALKEEPER_FOCUS_ATTRIBUTES, INTENSITIES, NO_FOCUS, OUTFIELD_FOCUS_ATTRIBUTES
from src.models.player import PlayerHiddenAttributes, PlayerVisibleAttributes
from src.models.tactics import TACTICAL_STYLES

PLACEHOLDER = re.compile(r"{(\w+)}")
HEBREW = re.compile("[֐-׿]")  # Hebrew Unicode block
CLASSIFIER_CATEGORIES = [
    "Core Starter (Keep)",
    "Rotation / Sub (Keep)",
    "Loan Out (Development)",
    "Sell High (False Potential)",
    "Sell / Offload",
]


class TestI18n(unittest.TestCase):
    def test_tables_have_identical_keys(self) -> None:
        self.assertEqual(set(i18n.EN) - set(i18n.HE), set(), "keys missing in Hebrew")
        self.assertEqual(set(i18n.HE) - set(i18n.EN), set(), "keys missing in English")

    def test_placeholders_match(self) -> None:
        for key, en in i18n.EN.items():
            self.assertEqual(set(PLACEHOLDER.findall(en)), set(PLACEHOLDER.findall(i18n.HE[key])), key)

    def test_hebrew_strings_are_hebrew(self) -> None:
        # Column abbreviations that are FM27 terms (CA / PA / IP / OOP) stay Latin on purpose.
        latin_ok = {"squad.col.ca", "squad.col.pa", "squad.col.headroom", "squad.col.ip", "squad.col.oop"}
        for key, text in i18n.HE.items():
            if key not in latin_ok:
                self.assertRegex(text, HEBREW, key)

    def test_tr_formats_and_falls_back(self) -> None:
        self.assertEqual(i18n.tr("status.imported", count=3, file="a.csv"),
                         "Imported file  ·  Loaded 3 players from a.csv.")
        self.assertEqual(i18n.tr("no.such.key"), "no.such.key")
        self.assertEqual(i18n.tr("toolbar.theme"), "Theme: {name}")  # unknown placeholders stay
        self.assertRegex(i18n.tr("toolbar.load", "he"), HEBREW)
        self.assertIn("FM27", i18n.tr("toolbar.load", "he"))

    def test_unsupported_language_raises(self) -> None:
        with self.assertRaises(ValueError):
            i18n.tr("toolbar.load", "fr")
        with self.assertRaises(ValueError):
            i18n.client_bundle("fr")

    def test_client_bundle(self) -> None:
        en, he = i18n.client_bundle("en"), i18n.client_bundle("he")
        self.assertEqual((en["dir"], he["dir"]), ("ltr", "rtl"))
        self.assertEqual(set(en["strings"]), set(i18n.EN))
        self.assertEqual(set(he["strings"]), set(i18n.EN))
        # Qt-era "&&" escapes are plain "&" in the browser.
        self.assertEqual(en["strings"]["tab.tactics"], "Tactical Pitch & Instructions")
        self.assertFalse(any("&&" in v for v in he["strings"].values()))
        # No invisible bidi control characters: the browser handles direction itself.
        self.assertFalse(any(re.search("[‪-‮]", v) for v in he["strings"].values()))
        self.assertEqual(en["attrs"]["off_the_ball"], "Off The Ball")
        self.assertEqual(he["attrs"]["off_the_ball"], i18n.ATTRIBUTES_HE["off_the_ball"])

    def test_domain_vocabularies_are_translated(self) -> None:
        focuses = set(OUTFIELD_FOCUS_ATTRIBUTES) | set(GOALKEEPER_FOCUS_ATTRIBUTES) | {NO_FOCUS}
        keys = (
            [f"training.focus.{f}" for f in focuses]
            + [f"training.intensity.{i}" for i in INTENSITIES]
            + [f"category.{c}" for c in CLASSIFIER_CATEGORIES]
            + [f"style.{s}" for s in TACTICAL_STYLES]
            + [f"subs.kind.{k}" for k in SCENARIO_MINUTES]
            + [f"bench.role.{r}" for r in ("backup_gk", "defence", "midfield", "attack", "utility")]
        )
        for key in keys:
            self.assertIn(key, i18n.EN)
            if not key.startswith(("style.", "subs.", "bench.")):
                self.assertRegex(i18n.HE[key], HEBREW, key)

    def test_every_attribute_has_a_hebrew_name(self) -> None:
        names = set(PlayerVisibleAttributes.__dataclass_fields__) | set(PlayerHiddenAttributes.__dataclass_fields__)
        names -= {"ca", "pa"}
        self.assertEqual(names - set(i18n.ATTRIBUTES_HE), set())
        self.assertEqual(i18n.attr_name("off_the_ball"), "Off The Ball")
        self.assertEqual(i18n.attr_name("off_the_ball", "he"), i18n.ATTRIBUTES_HE["off_the_ball"])

    def test_fm27_role_names_stay_english_in_hebrew_reasons(self) -> None:
        text = i18n.tr("training.reason.focus_gap", "he", role="Inside Forward", attrs="x")
        self.assertIn("Inside Forward", text)
        self.assertRegex(text, HEBREW)


if __name__ == "__main__":
    unittest.main()
