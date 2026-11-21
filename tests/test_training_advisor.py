"""Unit tests for individual training recommendations."""

from dataclasses import replace
from pathlib import Path
import unittest

from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.engine.training_advisor import (
    DOUBLE,
    GOALKEEPER_FOCUS_ATTRIBUTES,
    HALF,
    INTENSITIES,
    NO_FOCUS,
    NORMAL,
    OUTFIELD_FOCUS_ATTRIBUTES,
    ROLE_SOURCE_BEST_XI,
    ROLE_SOURCE_NATURAL,
    ROLE_SOURCE_SECOND_XI,
    TrainingAdvisor,
)
from src.memory.fallback_loader import generate_sample_squad
from src.models.player import Player, PlayerHiddenAttributes, PlayerVisibleAttributes

CFG = Path(__file__).resolve().parent.parent / "config"


def make_player(pid=1, age=22, ca=120, pa=150, prof=14, det=14, inj=6, positions=("MC",), gk=False, **visible):
    vis = PlayerVisibleAttributes(determination=det, **visible)
    hid = PlayerHiddenAttributes(ca=ca, pa=pa, professionalism=prof, injury_proneness=inj)
    return Player(player_id=pid, name=f"Test Player {pid}", age=age, positions=list(positions), is_gk=gk,
                  visible=vis, hidden=hid)


class TestTrainingAdvisor(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evaluator = RoleEvaluator(CFG / "roles_in_possession.json", CFG / "roles_out_possession.json")
        cls.advisor = TrainingAdvisor(cls.evaluator)
        cls.optimizer = SynergyOptimizer(CFG / "formations.json", cls.evaluator)

    def test_role_focus_follows_best_and_second_xi(self) -> None:
        squad = generate_sample_squad()
        lineup = self.optimizer.optimize(squad)
        recs = {r.player.player_id: r for r in self.advisor.recommend(squad, lineup)}
        self.assertEqual(len(recs), len(squad))
        for slot in lineup.best_xi:
            rec = recs[slot.player.player_id]
            self.assertEqual(rec.role_source, ROLE_SOURCE_BEST_XI)
            self.assertEqual(rec.role_focus, slot.ip_role)
        for slot in lineup.backup_xi:
            rec = recs[slot.player.player_id]
            self.assertEqual(rec.role_source, ROLE_SOURCE_SECOND_XI)
            self.assertEqual(rec.role_focus, slot.ip_role)
        in_xi = {s.player.player_id for s in lineup.best_xi + lineup.backup_xi}
        for pid, rec in recs.items():
            if pid not in in_xi:
                self.assertEqual(rec.role_source, ROLE_SOURCE_NATURAL)
                self.assertIn(rec.role_focus, self.evaluator.ip_roles)

    def test_outputs_are_valid_vocabulary(self) -> None:
        squad = generate_sample_squad()
        lineup = self.optimizer.optimize(squad)
        valid_focus = set(OUTFIELD_FOCUS_ATTRIBUTES) | set(GOALKEEPER_FOCUS_ATTRIBUTES) | {NO_FOCUS}
        for rec in self.advisor.recommend(squad, lineup):
            self.assertIn(rec.intensity, INTENSITIES)
            self.assertIn(rec.additional_focus, valid_focus)
            self.assertTrue(rec.reason_key.startswith("training.reason."))
            if rec.player.is_gk and rec.additional_focus != NO_FOCUS:
                self.assertIn(rec.additional_focus, GOALKEEPER_FOCUS_ATTRIBUTES)

    def test_recommend_orders_best_xi_first(self) -> None:
        squad = generate_sample_squad()
        lineup = self.optimizer.optimize(squad)
        sources = [r.role_source for r in self.advisor.recommend(squad, lineup)]
        rank = {ROLE_SOURCE_BEST_XI: 0, ROLE_SOURCE_SECOND_XI: 1, ROLE_SOURCE_NATURAL: 2}
        self.assertEqual(sources, sorted(sources, key=rank.get))

    def test_young_professional_prospect_gets_double_intensity(self) -> None:
        rec = self.advisor.recommend_player(make_player(age=19, ca=100, pa=150, prof=16, det=15, inj=5))
        self.assertEqual(rec.intensity, DOUBLE)
        self.assertEqual(rec.reason_key, "training.reason.develop")
        self.assertEqual(rec.reason_args["headroom"], 50)

    def test_prospect_with_weak_mentality_stays_normal(self) -> None:
        rec = self.advisor.recommend_player(make_player(age=19, ca=100, pa=150, prof=8, det=9))
        self.assertEqual(rec.intensity, NORMAL)
        self.assertEqual(rec.reason_key, "training.reason.mentality_limits")

    def test_injury_prone_player_gets_half_intensity(self) -> None:
        rec = self.advisor.recommend_player(make_player(age=20, ca=100, pa=160, prof=18, det=18, inj=16))
        self.assertEqual(rec.intensity, HALF)
        self.assertEqual(rec.reason_key, "training.reason.injury_risk")

    def test_veteran_gets_half_intensity(self) -> None:
        rec = self.advisor.recommend_player(make_player(age=33, ca=140, pa=142))
        self.assertEqual(rec.intensity, HALF)
        self.assertEqual(rec.reason_key, "training.reason.veteran")

    def test_player_at_ceiling_gets_no_additional_focus(self) -> None:
        rec = self.advisor.recommend_player(make_player(age=27, ca=140, pa=140, passing=5, vision=5))
        self.assertEqual(rec.additional_focus, NO_FOCUS)
        self.assertEqual(rec.reason_key, "training.reason.ceiling")

    def test_additional_focus_targets_biggest_role_gap(self) -> None:
        # A central midfielder whose passing/vision/technique are far below everything else.
        base = dict(age=26, ca=120, pa=150, positions=("MC",))
        strong = {a: 16 for a in ("first_touch", "dribbling", "acceleration", "pace", "agility", "stamina",
                                  "natural_fitness", "work_rate", "finishing", "off_the_ball", "composure",
                                  "long_shots", "positioning", "marking", "anticipation", "concentration",
                                  "tackling", "heading", "jumping_reach", "strength", "decisions", "teamwork")}
        player = make_player(passing=3, vision=3, technique=3, **base, **strong)
        rec = self.advisor.recommend_player(player)
        self.assertEqual(rec.additional_focus, "Passing")
        self.assertEqual(rec.reason_key, "training.reason.focus_gap")
        self.assertTrue(set(rec.focus_attributes) <= {"passing", "vision", "technique"})

    def test_goalkeeper_uses_goalkeeper_focus_groups(self) -> None:
        keeper = make_player(age=24, ca=110, pa=150, positions=("GK",), gk=True,
                             reflexes=6, one_on_ones=6, handling=6, kicking=16, throwing=16, passing=16)
        rec = self.advisor.recommend_player(keeper)
        self.assertIn(rec.additional_focus, GOALKEEPER_FOCUS_ATTRIBUTES)
        self.assertEqual(rec.additional_focus, "Shot Stopping")

    def test_recommend_without_lineup_uses_natural_roles(self) -> None:
        squad = generate_sample_squad()[:5]
        recs = self.advisor.recommend(squad)
        self.assertTrue(all(r.role_source == ROLE_SOURCE_NATURAL for r in recs))

    def test_player_is_not_mutated(self) -> None:
        player = make_player(age=19, ca=100, pa=150)
        snapshot = replace(player)
        self.advisor.recommend_player(player)
        self.assertEqual(player, snapshot)


if __name__ == "__main__":
    unittest.main()
