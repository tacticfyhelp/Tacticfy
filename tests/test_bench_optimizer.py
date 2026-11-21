"""Unit tests for the matchday bench and substitution planner."""

from pathlib import Path
import unittest

from src.engine.bench_optimizer import (
    ATTACK,
    DEFAULT_BENCH_SIZE,
    DEFENCE,
    MIDFIELD,
    SCENARIO_CHASE,
    SCENARIO_FATIGUE,
    SCENARIO_MINUTES,
    SCENARIO_PROTECT,
    BenchOptimizer,
    defensive_score,
    impact_score,
    late_game_factor,
)
from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.memory.fallback_loader import generate_sample_squad
from src.models.tactics import TACTICAL_STYLES

CFG = Path(__file__).resolve().parent.parent / "config"


class TestBenchOptimizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evaluator = RoleEvaluator(CFG / "roles_in_possession.json", CFG / "roles_out_possession.json")
        cls.optimizer = SynergyOptimizer(CFG / "formations.json", cls.evaluator)
        cls.bench = BenchOptimizer(cls.evaluator)

    def setUp(self) -> None:
        self.squad = generate_sample_squad()
        self.lineup = self.optimizer.optimize(self.squad)
        self.starter_ids = {a.player.player_id for a in self.lineup.best_xi}

    def test_default_bench_has_nine_distinct_non_starters(self) -> None:
        plan = self.bench.select_bench(self.squad, self.lineup)
        self.assertEqual(DEFAULT_BENCH_SIZE, 9)
        self.assertEqual(plan.size, 9)
        ids = [b.player.player_id for b in plan.bench]
        self.assertEqual(len(ids), 9)
        self.assertEqual(len(set(ids)), 9)
        self.assertTrue(self.starter_ids.isdisjoint(ids))

    def test_seven_sub_bench(self) -> None:
        plan = self.bench.select_bench(self.squad, self.lineup, size=7)
        self.assertEqual(len(plan.bench), 7)

    def test_exactly_one_backup_goalkeeper_first(self) -> None:
        plan = self.bench.select_bench(self.squad, self.lineup)
        roles = [b.bench_role for b in plan.bench]
        self.assertEqual(roles[0], "backup_gk")
        self.assertEqual(roles.count("backup_gk"), 1)
        self.assertTrue(plan.bench[0].player.is_gk)
        self.assertFalse(any(b.player.is_gk for b in plan.bench[1:]))

    def test_bench_covers_every_line(self) -> None:
        plan = self.bench.select_bench(self.squad, self.lineup)
        covered = {pos for b in plan.bench for pos in b.covered_positions}
        xi_positions = {a.position for a in self.lineup.best_xi}
        for line in (DEFENCE, MIDFIELD, ATTACK):
            if xi_positions & line:
                self.assertTrue(covered & line, f"no cover for line {sorted(line)}")
        # Every covered slot id really is a Best XI slot.
        slot_ids = {a.slot_id for a in self.lineup.best_xi}
        for b in plan.bench:
            self.assertTrue(set(b.covered_slots) <= slot_ids)

    def test_uncovered_slots_are_reported(self) -> None:
        plan = self.bench.select_bench(self.squad, self.lineup)
        covered_slots = {s for b in plan.bench for s in b.covered_slots}
        expected = [a.slot_id for a in self.lineup.best_xi if a.position != "GK" and a.slot_id not in covered_slots]
        self.assertEqual([s for s in plan.uncovered_slots if s in expected], expected)

    def test_substitution_scenarios_are_consistent(self) -> None:
        for style in TACTICAL_STYLES:
            lineup = self.optimizer.optimize(self.squad, tactical_style=style)
            starters = {a.player.player_id: a for a in lineup.best_xi}
            plan = self.bench.select_bench(self.squad, lineup)
            bench_ids = {b.player.player_id for b in plan.bench}
            self.assertTrue(plan.scenarios, style)
            for s in plan.scenarios:
                self.assertIn(s.kind, (SCENARIO_CHASE, SCENARIO_PROTECT, SCENARIO_FATIGUE))
                self.assertEqual(s.minute, SCENARIO_MINUTES[s.kind])
                self.assertIn(s.player_on.player_id, bench_ids)
                self.assertIn(s.player_off.player_id, starters)
                self.assertEqual(starters[s.player_off.player_id].slot_id, s.slot_id)
                self.assertFalse(s.player_on.is_gk)
                self.assertIn(s.ip_role, self.evaluator.ip_roles)
                self.assertIn(s.oop_role, self.evaluator.oop_roles)
                self.assertTrue(s.reason_key.startswith("subs.reason."))
                off_factor = late_game_factor(s.player_off)
                if s.kind == SCENARIO_CHASE:
                    self.assertGreater(impact_score(s.player_on), impact_score(s.player_off) * off_factor)
                if s.kind == SCENARIO_PROTECT:
                    self.assertGreater(defensive_score(s.player_on), defensive_score(s.player_off) * off_factor)

    def test_small_squad_returns_whole_remaining_pool(self) -> None:
        squad = self.squad[:14]
        lineup = self.optimizer.optimize(squad)
        plan = self.bench.select_bench(squad, lineup)
        self.assertEqual(len(plan.bench), 3)

    def test_invalid_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.bench.select_bench(self.squad, self.lineup, size=0)

    def test_cover_score_zero_for_unfamiliar_position(self) -> None:
        gk_slot = next(a for a in self.lineup.best_xi if a.position == "GK")
        outfielder = next(p for p in self.squad if not p.is_gk)
        self.assertEqual(self.bench.cover_score(outfielder, gk_slot), 0.0)


if __name__ == "__main__":
    unittest.main()
