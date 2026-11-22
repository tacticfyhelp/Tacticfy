"""Tacticfy v1.1.0-beta: FM Meta scoring, Exclude + fitness, Matchup context, 'Why this XI?' and translations."""

import copy
import datetime as dt
import json
from dataclasses import replace
from pathlib import Path
import unittest

from src.engine.bench_optimizer import BenchOptimizer
from src.engine.role_evaluator import META_WEIGHTS_GK, META_WEIGHTS_OUTFIELD, RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.memory.fallback_loader import generate_sample_squad
from src.memory.live_layout import LivePlayerRecord, record_to_player
from src.models.player import Player, PlayerVisibleAttributes
from src.models.tactics import (
    MATCHUP_AERIAL, MATCHUP_FAST_COUNTER, MATCHUP_FAVORITE, MATCHUP_NEUTRAL, MATCHUP_UNDERDOG, MATCHUPS,
    SCORING_BALANCED, SCORING_FM_META, SCORING_MODES,
)
from src.ui import i18n

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"
STYLE = "Balanced Tactical Meta"


def make_evaluator() -> RoleEvaluator:
    return RoleEvaluator(CFG / "roles_in_possession.json", CFG / "roles_out_possession.json")


def twin(base: Player, pid: int, name: str, **visible) -> Player:
    """Copy of ``base`` with a new id / name and some visible attributes overridden."""
    p = copy.deepcopy(base)
    p.player_id, p.name = pid, name
    p.visible = replace(p.visible, **visible)
    return p


class TestScoringModes(unittest.TestCase):
    def setUp(self) -> None:
        self.ev = make_evaluator()
        self.cb = next(p for p in generate_sample_squad() if p.positions[0] == "DC")
        self.role = next(n for n, r in self.ev.ip_roles.items() if r.slot_group == "DC")

    def test_fm_meta_is_the_default(self) -> None:
        self.assertEqual(SCORING_MODES[0], SCORING_FM_META)
        self.assertEqual(self.ev.scoring_mode, SCORING_FM_META)

    def test_fm_meta_adds_engine_attributes_to_role_weights(self) -> None:
        role = self.ev.ip_roles[self.role]
        self.ev.configure(SCORING_BALANCED)
        balanced = self.ev.attribute_weights(role, "DC")
        self.ev.configure(SCORING_FM_META)
        meta = self.ev.attribute_weights(role, "DC")
        for attr, w in META_WEIGHTS_OUTFIELD.items():
            self.assertAlmostEqual(meta[attr], balanced.get(attr, 0.0) + w, msg=attr)
        gk_role = next(r for r in self.ev.ip_roles.values() if r.slot_group == "GK")
        gk_meta = self.ev.attribute_weights(gk_role, "GK")
        self.assertTrue(set(META_WEIGHTS_GK) <= set(gk_meta))
        self.assertNotIn("dribbling", set(gk_meta) - set(gk_role.primary) - set(gk_role.secondary))

    def test_fm_meta_rewards_fast_sharp_players_more_than_balanced(self) -> None:
        quick = twin(self.cb, 9001, "Quick Thinker", pace=18, acceleration=18, anticipation=17, decisions=17)
        slow = twin(self.cb, 9002, "Slow Thinker", pace=8, acceleration=8, anticipation=9, decisions=9)
        gaps = {}
        for mode in (SCORING_BALANCED, SCORING_FM_META):
            self.ev.configure(mode)
            gaps[mode] = self.ev.score_ip_role(quick, self.role, "DC") - self.ev.score_ip_role(slow, self.role, "DC")
        self.assertGreater(gaps[SCORING_FM_META], gaps[SCORING_BALANCED])

    def test_unknown_mode_or_matchup_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.ev.configure("Turbo")
        with self.assertRaises(ValueError):
            self.ev.configure(SCORING_FM_META, "vs Martians")


class TestExcludeAndFitness(unittest.TestCase):
    def setUp(self) -> None:
        self.ev = make_evaluator()
        self.opt = SynergyOptimizer(CFG / "formations.json", self.ev)
        self.bench = BenchOptimizer(self.ev)
        self.squad = generate_sample_squad()

    def test_excluded_players_never_selected(self) -> None:
        first = self.opt.optimize(self.squad, STYLE)
        out = [a.player for a in first.best_xi[:3]]
        for p in out:
            p.excluded = True
        res = self.opt.optimize(self.squad, STYLE)
        selected = {a.player.player_id for a in res.best_xi + res.backup_xi}
        bench = {b.player.player_id for b in self.bench.select_bench(self.squad, res, 9).bench}
        for p in out:
            self.assertNotIn(p.player_id, selected | bench)
        self.assertEqual(res.excluded_count, 3)

    def test_too_many_exclusions_raise(self) -> None:
        for p in self.squad[:-10]:
            p.excluded = True
        with self.assertRaises(ValueError):
            self.opt.optimize(self.squad, STYLE)

    def test_fitness_penalty_and_alerts(self) -> None:
        p = self.squad[3]
        self.assertEqual(self.ev.fitness_status(p), (1.0, None))  # unknown fitness: never penalized
        p.match_sharpness, p.fatigue = 90, 0
        self.assertEqual(self.ev.fitness_status(p), (1.0, None))
        p.match_sharpness = 30
        factor, alert = self.ev.fitness_status(p)
        self.assertLess(factor, 0.97)
        self.assertEqual(alert, ("fitness.alert.sharpness", {"pct": 30}))
        p.fatigue = 900
        factor_both, alert = self.ev.fitness_status(p)
        self.assertLess(factor_both, factor)
        self.assertEqual(alert[0], "fitness.alert.both")
        self.ev.configure(factor_in_fitness=False)
        self.assertEqual(self.ev.fitness_status(p)[0], 1.0)  # toggle off: no penalty...
        self.assertIsNotNone(self.ev.fitness_status(p)[1])   # ...but the warning stays visible

    def test_exhausted_starter_is_benched_only_when_fitness_counts(self) -> None:
        base = self.opt.optimize(self.squad, STYLE, formation_filter="4-2-3-1 DM")
        star = max((a for a in base.best_xi if a.position != "GK"), key=lambda a: a.combined_score)
        star.player.match_sharpness, star.player.fatigue = 5, 1000
        fit = self.opt.optimize(self.squad, STYLE, formation_filter="4-2-3-1 DM", factor_in_fitness=True)
        slot = next(a for a in fit.best_xi if a.player.player_id == star.player.player_id) \
            if star.player.player_id in {a.player.player_id for a in fit.best_xi} else None
        if slot is not None:  # still starts (irreplaceable) - but penalized and flagged
            self.assertLess(slot.combined_score, star.combined_score)
            self.assertIsNotNone(slot.fitness_alert)
            self.assertTrue(any("Matchday Readiness" in w for w in fit.synergy_warnings))
        self.assertLess(fit.team_synergy_score, base.team_synergy_score)
        unfit = self.opt.optimize(self.squad, STYLE, formation_filter="4-2-3-1 DM", factor_in_fitness=False)
        same = next(a for a in unfit.best_xi if a.player.player_id == star.player.player_id)
        self.assertAlmostEqual(same.combined_score, star.combined_score, places=1)
        self.assertIsNotNone(same.fitness_alert)  # warning still shown with the toggle off

    def test_bench_flags_unfit_substitutes(self) -> None:
        res = self.opt.optimize(self.squad, STYLE)
        starters = {a.player.player_id for a in res.best_xi}
        sub = next(p for p in self.squad if p.player_id not in starters and not p.is_gk)
        sub.match_sharpness = 20
        plan = self.bench.select_bench(self.squad, self.opt.optimize(self.squad, STYLE), 9)
        flagged = [b for b in plan.bench if b.player.player_id == sub.player_id]
        for b in flagged:
            self.assertEqual(b.fitness_alert[0], "fitness.alert.sharpness")

    def test_live_record_maps_sharpness_and_fatigue(self) -> None:
        layout = json.loads((CFG / "offsets.json").read_text(encoding="utf-8"))["fm27_live_layout"]
        n_attr = len(layout["player_db_object"]["attribute_order"])
        rec = LivePlayerRecord(slot=0, uid=7, name="Test Player", ca=120, pa=150, positions=[1] * 14 + [20],
                               raw_attributes=[60] * n_attr, personality=[10] * 8, dob=dt.date(2000, 1, 1),
                               sharpness=6350, fatigue=-125, world_rep=5000)
        player = record_to_player(rec, layout, dt.date(2026, 11, 22))
        self.assertEqual(player.match_sharpness, 64)
        self.assertEqual(player.fatigue, -125)


class TestMatchup(unittest.TestCase):
    def setUp(self) -> None:
        self.ev = make_evaluator()
        self.opt = SynergyOptimizer(CFG / "formations.json", self.ev)
        self.squad = generate_sample_squad()

    def test_fast_counter_prefers_faster_centre_backs(self) -> None:
        cb = next(p for p in self.squad if p.positions[0] == "DC")
        role = next(n for n, r in self.ev.ip_roles.items() if r.slot_group == "DC")
        fast = twin(cb, 9101, "Fast CB", pace=18, acceleration=18)
        slow = twin(cb, 9102, "Slow CB", pace=9, acceleration=9)
        gaps = {}
        for m in (MATCHUP_NEUTRAL, MATCHUP_FAST_COUNTER):
            self.ev.configure(SCORING_FM_META, m)
            gaps[m] = self.ev.score_ip_role(fast, role, "DC") - self.ev.score_ip_role(slow, role, "DC")
        self.assertGreater(gaps[MATCHUP_FAST_COUNTER], gaps[MATCHUP_NEUTRAL])

    def test_aerial_prefers_taller_centre_backs(self) -> None:
        cb = next(p for p in self.squad if p.positions[0] == "DC")
        role = next(n for n, r in self.ev.oop_roles.items() if r.slot_group == "DC")
        tall = twin(cb, 9103, "Tall CB", jumping_reach=19, heading=18, strength=18)
        short = twin(cb, 9104, "Short CB", jumping_reach=8, heading=9, strength=9)
        gaps = {}
        for m in (MATCHUP_NEUTRAL, MATCHUP_AERIAL):
            self.ev.configure(SCORING_FM_META, m)
            gaps[m] = self.ev.score_oop_role(tall, role, "DC") - self.ev.score_oop_role(short, role, "DC")
        self.assertGreater(gaps[MATCHUP_AERIAL], gaps[MATCHUP_NEUTRAL])

    def test_team_instructions_adapt_to_the_matchup(self) -> None:
        lines = ["Much Lower", "Lower", "Standard", "Higher", "Much Higher"]
        blocks = ["Low Block", "Mid Block", "High Press"]
        style = "High-Scoring Attacking"
        neutral = self.opt.optimize(self.squad, style, matchup=MATCHUP_NEUTRAL).instructions
        counter = self.opt.optimize(self.squad, style, matchup=MATCHUP_FAST_COUNTER).instructions
        self.assertLess(lines.index(counter.out_of_possession["Defensive Line"]),
                        lines.index(neutral.out_of_possession["Defensive Line"]))
        self.assertEqual(counter.out_of_possession["Defensive Line Behaviour"], "Drop Off More")
        self.assertEqual(counter.in_transition["Defensive Transition"], "Regroup")

        aerial = self.opt.optimize(self.squad, style, matchup=MATCHUP_AERIAL).instructions
        self.assertEqual(aerial.out_of_possession["Cross Engagement"], "Stop Crosses")

        fav = self.opt.optimize(self.squad, STYLE, matchup=MATCHUP_FAVORITE).instructions
        self.assertEqual(fav.in_possession["Patience"], "Work Ball Into Box")
        self.assertEqual(fav.in_possession["Creative Freedom"], "More Expressive")

        neutral_bal = self.opt.optimize(self.squad, STYLE, matchup=MATCHUP_NEUTRAL).instructions
        under = self.opt.optimize(self.squad, STYLE, matchup=MATCHUP_UNDERDOG).instructions
        self.assertLess(blocks.index(under.out_of_possession["Line of Engagement"]),
                        blocks.index(neutral_bal.out_of_possession["Line of Engagement"]))
        self.assertEqual(under.in_transition["Defensive Transition"], "Regroup")
        for ins in (counter, aerial, fav, under):
            self.assertTrue(any(n.startswith("Matchup") for n in ins.tactical_notes))

    def test_every_matchup_optimizes(self) -> None:
        for m in MATCHUPS:
            res = self.opt.optimize(self.squad, STYLE, matchup=m)
            self.assertEqual(res.matchup, m)
            self.assertEqual(len(res.best_xi), 11)


class TestWhyThisXI(unittest.TestCase):
    def setUp(self) -> None:
        self.ev = make_evaluator()
        self.opt = SynergyOptimizer(CFG / "formations.json", self.ev)
        self.squad = generate_sample_squad()

    def test_formation_ranking_is_sorted_and_led_by_the_pick(self) -> None:
        res = self.opt.optimize(self.squad, STYLE, formation_filter=SynergyOptimizer.FILTER_STANDARD)
        scores = [s for _, s in res.formation_ranking]
        self.assertGreaterEqual(len(res.formation_ranking), 3)
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(res.formation_ranking[0], (res.formation_name, res.team_synergy_score))

    def test_runner_up_is_best_available_player_outside_the_xi(self) -> None:
        res = self.opt.optimize(self.squad, STYLE)
        slot = next(a for a in res.best_xi if a.position == "ST")
        exp = self.opt.explain_slot(res, slot, self.squad)
        starters = {a.player.player_id for a in res.best_xi}
        self.assertIsNotNone(exp.runner_up)
        self.assertNotIn(exp.runner_up.player_id, starters)
        self.assertGreaterEqual(exp.gap, 0.0)
        self.assertEqual(len(exp.top_attributes), 5)
        shares = [c.share for c in exp.top_attributes]
        self.assertEqual(shares, sorted(shares, reverse=True))

    def test_drivers_name_the_attribute_that_decided_the_slot(self) -> None:
        res = self.opt.optimize(self.squad, STYLE)
        slot = next(a for a in res.best_xi if a.position == "ST")
        # A clone that is identical except for much lower Pace/Acceleration and Consistency.
        rival = twin(slot.player, 9301, "Slow Clone",
                     pace=max(1, slot.player.visible.pace - 8), acceleration=max(1, slot.player.visible.acceleration - 8))
        rival.hidden = replace(rival.hidden, consistency=max(1, slot.player.hidden.consistency - 8))
        cfg = self.opt._slot_config(res, slot.slot_id)
        drivers = self.opt.compare_players(slot.player, rival, cfg, res)
        groups = [d.attrs for d in drivers]
        self.assertEqual(groups[0], ("pace", "acceleration"))
        self.assertGreater(drivers[0].delta, 0.5)
        self.assertIn(("consistency",), groups)
        self.assertTrue(all(d.delta > 0 for d in drivers))

    def test_explanation_respects_the_result_context(self) -> None:
        res = self.opt.optimize(self.squad, STYLE, scoring_mode=SCORING_BALANCED, matchup=MATCHUP_AERIAL)
        self.ev.configure(SCORING_FM_META, MATCHUP_NEUTRAL)  # something else ran in between
        self.opt.explain_slot(res, res.best_xi[1], self.squad)
        self.assertEqual((self.ev.scoring_mode, self.ev.matchup), (SCORING_BALANCED, MATCHUP_AERIAL))


class TestV11Translations(unittest.TestCase):
    NEW_KEYS = [
        "tactics.scoring", "tactics.scoring_tip", "tactics.matchup", "tactics.matchup_tip", "tactics.fitness",
        "tactics.fitness_tip", "tactics.summary.excluded", "fitness.alert.sharpness", "fitness.alert.fatigue",
        "fitness.alert.both", "fitness.detail", "fitness.ready", "fitness.unknown", "fitness.penalty", "why.title",
        "why.top_attrs", "why.beat", "why.locked", "why.drivers", "why.no_drivers", "why.no_runner_up",
        "why.formations", "why.formation_gap", "why.formation_best", "squad.col.exclude", "squad.exclude_tip",
        "squad.lock_tip", "status.too_many_excluded",
    ]

    def tearDown(self) -> None:
        i18n.set_language("en")

    def test_new_keys_exist_in_english_and_hebrew(self) -> None:
        for key in self.NEW_KEYS:
            self.assertIn(key, i18n.EN, key)
            self.assertIn(key, i18n.HE, key)
            self.assertNotEqual(i18n.EN[key], i18n.HE[key], key)

    def test_modes_matchups_and_drivers_are_translated(self) -> None:
        for mode in SCORING_MODES:
            self.assertIn(f"scoring.{mode}", i18n.HE)
        for m in MATCHUPS:
            self.assertIn(f"matchup.{m}", i18n.HE)
        for d in ("ca", "familiarity", "consistency", "fitness", "foot"):
            self.assertIn(f"why.driver.{d}", i18n.HE)
        i18n.set_language("he")
        self.assertIn("מהירות", i18n.tr_driver(("pace", "acceleration")))
        self.assertIn("פייבוריט", i18n.tr_matchup(MATCHUP_FAVORITE))
        self.assertIn("30", i18n.tr_fitness(("fitness.alert.sharpness", {"pct": 30})))
        i18n.set_language("en")
        self.assertEqual(i18n.tr_driver(("pace", "acceleration")), "Pace/Acceleration")
        self.assertEqual(i18n.tr_scoring(SCORING_FM_META), "FM Meta")
        self.assertEqual(i18n.tr_fitness(None), "")


if __name__ == "__main__":
    unittest.main()
