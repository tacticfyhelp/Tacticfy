"""Unit tests for the English / Hebrew UI translation tables."""

import re
import unittest

from src.engine.bench_optimizer import SCENARIO_MINUTES
from src.engine.training_advisor import GOALKEEPER_FOCUS_ATTRIBUTES, INTENSITIES, NO_FOCUS, OUTFIELD_FOCUS_ATTRIBUTES
from src.models.player import PlayerHiddenAttributes, PlayerVisibleAttributes
from src.models.tactics import TACTICAL_STYLES
from src.ui import i18n

PLACEHOLDER = re.compile(r"{(\w+)}")
HEBREW = re.compile("[\u0590-\u05ff]")  # Hebrew Unicode block
CLASSIFIER_CATEGORIES = [
    "Core Starter (Keep)",
    "Rotation / Sub (Keep)",
    "Loan Out (Development)",
    "Sell High (False Potential)",
    "Sell / Offload",
]


class TestI18n(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("en")

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
        # Unknown placeholders are left untouched instead of raising.
        self.assertEqual(i18n.tr("toolbar.theme"), "Theme: {name}")

    def test_hebrew_output_is_rtl_embedded(self) -> None:
        i18n.set_language("he")
        self.assertTrue(i18n.is_rtl())
        text = i18n.tr("toolbar.load")
        self.assertTrue(text.startswith("‫") and text.endswith("‬"))
        self.assertIn("FM27", text)
        self.assertEqual(i18n.ltr("Inside Forward"), "‪Inside Forward‬")
        i18n.set_language("en")
        self.assertFalse(i18n.is_rtl())
        self.assertEqual(i18n.tr("toolbar.load"), "Load from FM27")
        self.assertEqual(i18n.ltr("Inside Forward"), "Inside Forward")

    def test_unsupported_language_raises(self) -> None:
        with self.assertRaises(ValueError):
            i18n.set_language("fr")
        self.assertEqual(i18n.current_language(), "en")

    def test_domain_vocabularies_are_translated(self) -> None:
        focuses = set(OUTFIELD_FOCUS_ATTRIBUTES) | set(GOALKEEPER_FOCUS_ATTRIBUTES) | {NO_FOCUS}
        for focus in focuses:
            self.assertIn(f"training.focus.{focus}", i18n.EN)
        for intensity in INTENSITIES:
            self.assertIn(f"training.intensity.{intensity}", i18n.EN)
        for category in CLASSIFIER_CATEGORIES:
            self.assertIn(f"category.{category}", i18n.EN)
        for style in TACTICAL_STYLES:
            self.assertIn(f"style.{style}", i18n.EN)
        for kind in SCENARIO_MINUTES:
            self.assertIn(f"subs.kind.{kind}", i18n.EN)
        for role in ("backup_gk", "defence", "midfield", "attack", "utility"):
            self.assertIn(f"bench.role.{role}", i18n.EN)
        i18n.set_language("he")
        for focus in focuses:
            self.assertRegex(i18n.tr_focus(focus), HEBREW)
        for intensity in INTENSITIES:
            self.assertRegex(i18n.tr_intensity(intensity), HEBREW)
        for category in CLASSIFIER_CATEGORIES:
            self.assertRegex(i18n.tr_category(category), HEBREW)

    def test_every_attribute_has_a_hebrew_name(self) -> None:
        names = set(PlayerVisibleAttributes.__dataclass_fields__) | set(PlayerHiddenAttributes.__dataclass_fields__)
        names -= {"ca", "pa"}
        self.assertEqual(names - set(i18n.ATTRIBUTES_HE), set())
        self.assertEqual(i18n.tr_attr("off_the_ball"), "Off The Ball")
        i18n.set_language("he")
        self.assertEqual(i18n.tr_attr("off_the_ball"), i18n.ATTRIBUTES_HE["off_the_ball"])

    def test_fm27_role_names_stay_english_in_hebrew_reasons(self) -> None:
        i18n.set_language("he")
        text = i18n.tr_reason("training.reason.focus_gap", {"role": "Inside Forward", "attrs": ["finishing"]})
        self.assertIn("Inside Forward", text)
        self.assertIn(i18n.ATTRIBUTES_HE["finishing"], text)  # attribute names are translated
        self.assertRegex(text, HEBREW)

    def test_button_text_escapes_ampersand(self) -> None:
        self.assertEqual(i18n.tr_button("tactics.mode.bench"), "Bench && Subs")

    def test_bidi_helpers_mirror_in_hebrew(self) -> None:
        self.assertEqual(i18n.bidi_row(["a", "b"]), "ab")
        self.assertNotIn("align", i18n.table_open())
        i18n.set_language("he")
        self.assertEqual(i18n.bidi_row(["a", "b"]), "ba")
        self.assertIn("align='right'", i18n.table_open())


if __name__ == "__main__":
    unittest.main()
