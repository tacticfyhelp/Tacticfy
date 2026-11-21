"""Guards that roles, formations and generated instructions use the official FM27 vocabulary.

config/fm27_tactics_reference.json is extracted from the installed game by
tools/extract_fm27_tactics.py (RolesData / TacticTeamInstructionData / PlayerInstructionEntry).
"""

import json
from pathlib import Path
import unittest

from src.engine import instructions_gen, role_evaluator
from src.engine.instructions_gen import NO_PI_TWEAKS, fm27_catalogue
from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.memory.fallback_loader import generate_sample_squad
from src.models.tactics import TACTICAL_STYLES

CFG = Path(__file__).resolve().parent.parent / "config"
LEGACY_NAMES = {
    "Mezzala", "Anchor", "Regista", "Enganche", "Segundo Volante", "Ball-Winning Midfielder",
    "Ball Winning Midfielder", "Complete Forward", "Defensive Winger", "Wide Target Forward",
    "No-Nonsense Full-Back", "Inverted Winger", "Inverted Wing-Back", "Advanced Forward", "Pressing Forward",
    "Shadow Striker", "Sweeper Keeper (Support)", "Ball Playing Defender", "Central Defender",
}


class TestFM27Vocabulary(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ref = json.loads((CFG / "fm27_tactics_reference.json").read_text(encoding="utf-8"))
        cls.ip_names = {r["name"] for r in cls.ref["in_possession_roles"]}
        cls.oop_names = {r["name"] for r in cls.ref["out_of_possession_roles"]}
        cls.evaluator = RoleEvaluator(CFG / "roles_in_possession.json", CFG / "roles_out_possession.json")
        cls.optimizer = SynergyOptimizer(CFG / "formations.json", cls.evaluator)

    def test_reference_matches_game_counts(self) -> None:
        self.assertEqual(len(self.ip_names), 40)
        self.assertEqual(len(self.oop_names), 39)
        self.assertEqual(len({t["title"] for t in self.ref["team_instructions"]}), 27)
        self.assertEqual(len(self.ref["player_instructions"]), 17)
        self.assertEqual(len(self.ref["mentalities"]), 7)

    def test_role_configs_are_exactly_fm27_roles(self) -> None:
        self.assertEqual(set(self.evaluator.ip_roles), self.ip_names)
        self.assertEqual(set(self.evaluator.oop_roles), self.oop_names)
        self.assertFalse(LEGACY_NAMES & (set(self.evaluator.ip_roles) | set(self.evaluator.oop_roles)))

    def test_formation_slots_use_fm27_roles(self) -> None:
        for form in self.optimizer.formations.values():
            for slot in form.slots:
                self.assertTrue(set(slot.ip_roles) <= self.ip_names, (form.name, slot.slot_id, slot.ip_roles))
                self.assertTrue(set(slot.oop_roles) <= self.oop_names, (form.name, slot.slot_id, slot.oop_roles))

    def test_engine_role_sets_are_fm27_names(self) -> None:
        for name_set in (role_evaluator.TOUCHLINE_ROLES, role_evaluator.INVERTED_ROLES,
                         instructions_gen.CREATOR_ROLES, instructions_gen.PLAYMAKER_ROLES,
                         instructions_gen.HOLDING_ROLES, instructions_gen.TOUCHLINE_CROSSERS_BYLINE,
                         instructions_gen.TOUCHLINE_CROSSERS_DEEP, instructions_gen.INVERTING_ROLES,
                         instructions_gen.UNDERLAPPING_ROLES, instructions_gen.LATE_RUNNER_ROLES,
                         instructions_gen.TARGET_ROLES):
            self.assertTrue(set(name_set) <= self.ip_names, set(name_set) - self.ip_names)

    def test_generated_instructions_use_fm27_tiles(self) -> None:
        team, _, player, mentalities = fm27_catalogue()
        squad = generate_sample_squad()
        for style in TACTICAL_STYLES:
            for formation_filter in ("standard", "all"):
                res = self.optimizer.optimize(squad, tactical_style=style, formation_filter=formation_filter)
                ins = res.instructions
                self.assertIn(ins.mentality, mentalities)
                for block in (ins.in_possession, ins.in_transition, ins.out_of_possession):
                    for tile, setting in block.items():
                        self.assertIn(tile, team, f"{style}: unknown team tile {tile!r}")
                        self.assertIn(setting, team[tile], f"{style}: {tile!r} has no setting {setting!r}")
                for slot in res.best_xi:
                    self.assertIn(slot.ip_role, self.ip_names)
                    self.assertIn(slot.oop_role, self.oop_names)
                    self.assertTrue(slot.individual_instructions)
                    for pi in slot.individual_instructions:
                        if pi == NO_PI_TWEAKS:
                            continue
                        tile, _, setting = pi.partition(": ")
                        self.assertIn(tile, player, f"unknown player instruction tile in {pi!r}")
                        self.assertIn(setting, player[tile], f"invalid setting in {pi!r}")

    def test_invalid_instruction_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            instructions_gen._check_team("Passing Directness", "Much Shorter")  # FM24 title
        with self.assertRaises(ValueError):
            instructions_gen._check_player("Forward Runs", "Get Further Forward")  # FM24 PI


if __name__ == "__main__":
    unittest.main()
