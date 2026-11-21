"""Unit tests for the Dual-Phase Tactical & Synergy Optimizer."""

from pathlib import Path
import unittest

from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.memory.fallback_loader import generate_sample_squad
from src.models.tactics import TACTICAL_STYLES


class TestSynergyOptimizer(unittest.TestCase):
    """Validate Best XI, Backup XI, IP/OOP dual-phase roles, and instructions."""

    def setUp(self) -> None:
        cfg_dir = Path(__file__).resolve().parent.parent / "config"
        self.evaluator = RoleEvaluator(
            cfg_dir / "roles_in_possession.json",
            cfg_dir / "roles_out_possession.json",
        )
        self.optimizer = SynergyOptimizer(cfg_dir / "formations.json", self.evaluator)
        self.squad = generate_sample_squad()

    def test_best_and_backup_xi_disjoint(self) -> None:
        res = self.optimizer.optimize(self.squad, tactical_style="High-Scoring Attacking")
        self.assertEqual(len(res.best_xi), 11)
        self.assertEqual(len(res.backup_xi), 11)
        starter_ids = {s.player.player_id for s in res.best_xi}
        backup_ids = {b.player.player_id for b in res.backup_xi}
        self.assertEqual(len(starter_ids), 11)
        self.assertEqual(len(backup_ids), 11)
        self.assertTrue(starter_ids.isdisjoint(backup_ids))

    def test_locked_formation_and_locked_player(self) -> None:
        # Lock a young prospect and a specific formation
        target = next(p for p in self.squad if p.name == "Francesco Camarda")
        target.locked_starter = True
        res = self.optimizer.optimize(
            self.squad,
            tactical_style="Proactive Possession",
            locked_formation="4-3-3 DM Wide",
            big_match_mode=True,
        )
        self.assertEqual(res.formation_name, "4-3-3 DM Wide")
        starter_ids = {s.player.player_id for s in res.best_xi}
        self.assertIn(target.player_id, starter_ids)

    def test_all_tactical_styles_generate_instructions(self) -> None:
        for style in TACTICAL_STYLES:
            res = self.optimizer.optimize(self.squad, tactical_style=style)
            self.assertTrue(res.instructions.in_possession)
            self.assertTrue(res.instructions.in_transition)
            self.assertTrue(res.instructions.out_of_possession)
            for slot in res.best_xi:
                self.assertTrue(slot.ip_role)
                self.assertTrue(slot.oop_role)
                self.assertTrue(slot.individual_instructions)


if __name__ == "__main__":
    unittest.main()
