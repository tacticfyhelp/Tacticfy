"""Global Best XI & Backup XI optimizer with Team Synergy and Dual-Phase evaluation.

v1.1 layers on top of the role scores:
  * Scoring Mode (FM Meta / Balanced) and opponent Matchup - attribute weight layers in RoleEvaluator.
  * Factor in Fitness - live Match Sharpness / Fatigue multiplier on every slot score.
  * Exclude - excluded players never enter Best XI, Second XI or the bench.
  * "Why this XI?" - per-slot attribute contributions and a counterfactual comparison with the runner-up.
"""

from dataclasses import replace
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.engine.instructions_gen import InstructionsGenerator
from src.engine.role_evaluator import RoleEvaluator
from src.models.player import Player, PlayerVisibleAttributes
from src.models.tactics import (
    MATCHUP_AERIAL, MATCHUP_FAST_COUNTER, MATCHUP_FAVORITE, MATCHUP_NEUTRAL, MATCHUP_UNDERDOG,
    SCORING_FM_META, AssignedSlot, FormationConfig, FormationSlot, LineupResult, ScoreDriver, SlotExplanation,
)

IP_WEIGHT, OOP_WEIGHT = 0.58, 0.42

# Attribute groups that read as one idea in the runner-up comparison ("+3.8 Pace/Accel").
COMBINED_ATTRIBUTE_GROUPS: Tuple[Tuple[str, ...], ...] = (("pace", "acceleration"),)
# Non-attribute drivers (pseudo keys, translated by the UI).
DRIVER_CA, DRIVER_FAMILIARITY, DRIVER_CONSISTENCY, DRIVER_FITNESS, DRIVER_FOOT = (
    "ca", "familiarity", "consistency", "fitness", "foot")
MIN_DRIVER_POINTS = 0.15


def eligible_players(squad: Iterable[Player]) -> List[Player]:
    """Players available for selection (not excluded)."""
    return [p for p in squad if not p.excluded]


class SynergyOptimizer:
    """Solves optimal formations, Best XI, Backup XI, and IP/OOP role pairings."""

    FILTER_STANDARD = "standard"
    FILTER_ALL = "all"

    def __init__(self, formations_path: Path, evaluator: RoleEvaluator) -> None:
        self.evaluator = evaluator
        self.formations: Dict[str, FormationConfig] = self._load_formations(formations_path)
        self.instructions_gen = InstructionsGenerator()
        self._assign_cache: Dict[tuple, AssignedSlot] = {}

    @staticmethod
    def _load_formations(path: Path) -> Dict[str, FormationConfig]:
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        out: Dict[str, FormationConfig] = {}
        for f_name, cfg in raw.items():
            slots = [
                FormationSlot(
                    slot_id=s["slot_id"],
                    position=s["position"],
                    side=s["side"],
                    ip_roles=s["ip_roles"],
                    oop_roles=s["oop_roles"],
                    ip_xy=tuple(s["ip_xy"]) if "ip_xy" in s else None,
                    oop_xy=tuple(s["oop_xy"]) if "oop_xy" in s else None,
                )
                for s in cfg["slots"]
            ]
            out[f_name] = FormationConfig(
                name=f_name,
                style_affinity=cfg.get("style_affinity", {}),
                slots=slots,
                category=cfg.get("category", "standard"),
            )
        return out

    def _best_slot_assignment(
        self,
        player: Player,
        slot: FormationSlot,
        tactical_style: str,
        big_match_mode: bool,
    ) -> AssignedSlot:
        """Select optimal IP + OOP role pair for a given player in a specific slot."""
        best_score = -1e9
        best_assign: Optional[AssignedSlot] = None
        fitness, fitness_alert = self.evaluator.fitness_status(player)

        for ip_r in slot.ip_roles:
            ip_score = self.evaluator.score_ip_role(
                player, ip_r, slot.position, big_match_mode, tactical_style, side=slot.side
            )
            ip_def = self.evaluator.ip_roles[ip_r]
            ip_coords = (self.evaluator.mirror_x_for_side(ip_def.x, slot.side), ip_def.y)

            for oop_r in slot.oop_roles:
                oop_score = self.evaluator.score_oop_role(
                    player, oop_r, slot.position, big_match_mode, tactical_style
                )
                oop_def = self.evaluator.oop_roles[oop_r]
                oop_coords = (self.evaluator.mirror_x_for_side(oop_def.x, slot.side), oop_def.y)

                dist, penalty, alert = self.evaluator.evaluate_transition_load(
                    player, ip_r, oop_r, slot.side
                )
                combined = ((ip_score * IP_WEIGHT + oop_score * OOP_WEIGHT) - penalty) * fitness

                if combined > best_score:
                    best_score = combined
                    best_assign = AssignedSlot(
                        slot_id=slot.slot_id,
                        position=slot.position,
                        side=slot.side,
                        player=player,
                        ip_role=ip_r,
                        ip_score=ip_score,
                        ip_coords=ip_coords,
                        oop_role=oop_r,
                        oop_score=oop_score,
                        oop_coords=oop_coords,
                        combined_score=round(combined, 1),
                        transition_distance=dist,
                        transition_alert=alert,
                        fitness_alert=fitness_alert,
                        fitness_factor=fitness,
                    )
        assert best_assign is not None
        return best_assign

    def _solve_eleven(
        self,
        players: List[Player],
        formation: FormationConfig,
        tactical_style: str,
        big_match_mode: bool,
        locked_ids: Set[int],
    ) -> List[AssignedSlot]:
        """Solve 11-player assignment using Hungarian algorithm (linear_sum_assignment)."""
        if len(players) < 11:
            raise ValueError(f"Need at least 11 players to build a lineup, got {len(players)}.")

        num_players = len(players)
        num_slots = len(formation.slots)
        cost_matrix = np.zeros((num_players, num_slots), dtype=float)
        cache: Dict[Tuple[int, int], AssignedSlot] = {}

        for p_idx, player in enumerate(players):
            lock_bonus = 250.0 if player.player_id in locked_ids else 0.0
            for s_idx, slot in enumerate(formation.slots):
                key = (player.player_id, slot.slot_id, slot.position, slot.side,
                       tuple(slot.ip_roles), tuple(slot.oop_roles))
                template = self._assign_cache.get(key)
                if template is None:
                    template = self._best_slot_assignment(player, slot, tactical_style, big_match_mode)
                    self._assign_cache[key] = template
                # Fresh copy: instructions are written onto the chosen slots later.
                assigned = replace(
                    template,
                    individual_instructions=[],
                    ip_display=slot.ip_xy,
                    oop_display=slot.oop_xy,
                )
                cache[(p_idx, s_idx)] = assigned
                # Negate for minimization
                cost_matrix[p_idx, s_idx] = -(assigned.combined_score + lock_bonus)

        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        solved: List[AssignedSlot] = [None] * num_slots  # type: ignore[list-item]
        for r, c in zip(row_ind, col_ind):
            solved[c] = cache[(r, c)]

        return solved

    def _evaluate_team_synergy(
        self,
        lineup: List[AssignedSlot],
        formation: FormationConfig,
        tactical_style: str,
        matchup: str = MATCHUP_NEUTRAL,
    ) -> Tuple[float, List[str]]:
        """Apply Team Synergy rules: spatial collisions, midfield balance, CB pace and matchup checks."""
        base_avg = sum(a.combined_score for a in lineup) / len(lineup)
        synergy_bonus = 0.0
        warnings: List[str] = []

        # 1. Midfield Triangle Balance (holder + runner + creator)
        all_tags: List[str] = []
        for a in lineup:
            all_tags.extend(self.evaluator.ip_roles[a.ip_role].synergy_tags)

        has_holder = "holder" in all_tags or "screen" in all_tags
        has_runner = "runner" in all_tags or "box_crasher" in all_tags
        has_creator = "creator" in all_tags or "line_breaker" in all_tags

        if has_holder and has_runner and has_creator:
            synergy_bonus += 3.5
        else:
            missing = []
            if not has_holder:
                missing.append("defensive holder")
            if not has_runner:
                missing.append("progressive runner")
            if not has_creator:
                missing.append("primary creator")
            synergy_bonus -= 2.5 * len(missing)
            warnings.append(f"Midfield balance gap: missing {', '.join(missing)}.")

        # 1b. FM27 role duplication: one Free Role, and no more than two playmakers
        ip_names = [a.ip_role for a in lineup]
        free_roles = ip_names.count("Free Role")
        playmakers = sum(ip_names.count(r) for r in (
            "Deep-Lying Playmaker", "Midfield Playmaker", "Advanced Playmaker", "Box-To-Box Playmaker"))
        if free_roles > 1:
            synergy_bonus -= 2.0 * (free_roles - 1)
            warnings.append(f"Role Overlap: {free_roles} Free Roles leave the shape without structure.")
        if playmakers > 2:
            synergy_bonus -= 1.5 * (playmakers - 2)
            warnings.append(f"Role Overlap: {playmakers} playmakers compete for the ball.")

        # 2. Spatial Non-Collision & Width Check (left and right flanks)
        for side_label in ("L", "R"):
            flank_slots = [a for a in lineup if a.side == side_label and a.position in ("DL", "DR", "WBL", "WBR", "ML", "MR", "AML", "AMR")]
            if len(flank_slots) >= 2:
                half_spaces = [self.evaluator.ip_roles[a.ip_role].half_space for a in flank_slots]
                if all(hs == "half_space" for hs in half_spaces):
                    synergy_bonus -= 2.5
                    warnings.append(
                        f"Uncovered Flank Risk ({side_label}): both wide players cut inside with no width holder."
                    )
                elif "wide" in half_spaces and "half_space" in half_spaces:
                    synergy_bonus += 1.5

        # 3. Defensive Line Speed vs High Press Compatibility
        cbs = [a for a in lineup if a.position == "DC"]
        if cbs:
            avg_cb_pace = sum(c.player.visible.pace for c in cbs) / len(cbs)
            high_line_style = tactical_style in ("High-Scoring Attacking", "Proactive Possession")
            if high_line_style and avg_cb_pace < 11.5:
                synergy_bonus -= 3.0
                warnings.append(
                    f"High-Line Vulnerability: Average CB Pace is {avg_cb_pace:.1f}. Consider Mid-Block OOP line."
                )
            elif high_line_style and avg_cb_pace >= 14.0:
                synergy_bonus += 1.8

        # 3b. Opponent matchup checks
        bonus, matchup_warnings = self._matchup_synergy(lineup, matchup)
        synergy_bonus += bonus
        warnings.extend(matchup_warnings)

        # 4. Style Affinity multiplier
        style_mult = formation.style_affinity.get(tactical_style, 1.0)
        final_synergy = round((base_avg + synergy_bonus) * style_mult, 2)
        return final_synergy, warnings

    @staticmethod
    def _matchup_synergy(lineup: List[AssignedSlot], matchup: str) -> Tuple[float, List[str]]:
        """Team-level fit for the opponent matchup (bonus, warnings)."""
        def avg(players: List[Player], attrs: Tuple[str, ...]) -> Optional[float]:
            if not players:
                return None
            return sum(sum(p.visible.get(a) for a in attrs) / len(attrs) for p in players) / len(players)

        cbs = [a.player for a in lineup if a.position == "DC"]
        attackers = [a.player for a in lineup if a.position in ("AML", "AMR", "AMC", "ST")]
        outfield = [a.player for a in lineup if a.position != "GK"]
        if matchup == MATCHUP_FAST_COUNTER:
            v = avg(cbs, ("pace", "acceleration"))
            if v is not None and v < 12.0:
                return -2.5, [f"Counter Exposure: centre-backs average {v:.1f} Pace/Acceleration against a fast counter."]
            if v is not None and v >= 14.0:
                return 1.5, []
        elif matchup == MATCHUP_AERIAL:
            v = avg(cbs, ("jumping_reach", "heading", "strength"))
            if v is not None and v < 13.0:
                return -2.5, [f"Aerial Exposure: centre-backs average {v:.1f} Jumping Reach/Heading/Strength against a direct side."]
            if v is not None and v >= 15.0:
                return 1.5, []
        elif matchup == MATCHUP_FAVORITE:
            v = avg(attackers, ("flair", "dribbling", "off_the_ball", "vision"))
            if v is not None and v < 11.0:
                return -1.5, [f"Low-Block Risk: attackers average {v:.1f} Flair/Dribbling/Off The Ball/Vision to unlock a deep block."]
            if v is not None and v >= 14.0:
                return 1.5, []
        elif matchup == MATCHUP_UNDERDOG:
            v = avg(outfield, ("work_rate", "positioning", "concentration"))
            if v is not None and v < 11.0:
                return -1.5, [f"Underdog Risk: XI averages {v:.1f} Work Rate/Positioning/Concentration against a stronger side."]
            if v is not None and v >= 14.0:
                return 1.5, []
        return 0.0, []

    def candidate_formations(self, formation_filter: str = FILTER_ALL) -> List[FormationConfig]:
        """Resolve a formation filter: "standard", "all", a category name, or one formation name."""
        if formation_filter in self.formations:
            return [self.formations[formation_filter]]
        if formation_filter in (None, "", self.FILTER_ALL):
            return list(self.formations.values())
        pool = [f for f in self.formations.values() if f.category == formation_filter]
        if not pool:
            raise ValueError(
                f"Unknown formation filter {formation_filter!r}: use 'standard', 'all', a category, "
                f"or one of {sorted(self.formations)}."
            )
        return pool

    def optimize(
        self,
        squad: List[Player],
        tactical_style: str = "Balanced Tactical Meta",
        locked_formation: Optional[str] = None,
        big_match_mode: bool = False,
        formation_filter: str = FILTER_ALL,
        scoring_mode: str = SCORING_FM_META,
        matchup: str = MATCHUP_NEUTRAL,
        factor_in_fitness: bool = True,
    ) -> LineupResult:
        """Find the optimal formation, Best XI, Backup XI, and Instructions.

        ``formation_filter`` is "standard" (classic shapes only), "all" (standard + tactical meta),
        or a specific formation name. ``locked_formation`` is kept for backward compatibility and
        takes precedence when given. Excluded players are never selected.
        """
        self.evaluator.configure(scoring_mode, matchup, factor_in_fitness)
        pool = eligible_players(squad)
        if len(pool) < 11:
            raise ValueError(f"Need at least 11 available players to build a lineup, got {len(pool)} "
                             f"({len(squad) - len(pool)} excluded).")
        locked_ids = {p.player_id for p in pool if p.locked_starter}
        self._assign_cache = {}  # scores depend on style / mode / matchup / fitness / current attributes

        if locked_formation and locked_formation in self.formations:
            candidates = [self.formations[locked_formation]]
        else:
            candidates = self.candidate_formations(formation_filter)

        best_score = -1e9
        best_formation: Optional[FormationConfig] = None
        best_xi: List[AssignedSlot] = []
        best_warnings: List[str] = []
        ranking: List[Tuple[str, float]] = []

        for form in candidates:
            xi = self._solve_eleven(pool, form, tactical_style, big_match_mode, locked_ids)
            syn_score, warnings = self._evaluate_team_synergy(xi, form, tactical_style, matchup)
            ranking.append((form.name, syn_score))
            if syn_score > best_score:
                best_score = syn_score
                best_formation = form
                best_xi = xi
                best_warnings = warnings

        assert best_formation is not None
        ranking.sort(key=lambda fs: -fs[1])
        starter_ids = {a.player.player_id for a in best_xi}
        remaining = [p for p in pool if p.player_id not in starter_ids]

        backup_xi: List[AssignedSlot] = []
        dropoff_by_slot: Dict[str, float] = {}
        if len(remaining) >= 11:
            backup_xi = self._solve_eleven(remaining, best_formation, tactical_style, big_match_mode, set())
            backup_map = {b.slot_id: b for b in backup_xi}
            for starter in best_xi:
                b = backup_map.get(starter.slot_id)
                if b:
                    dropoff_by_slot[starter.slot_id] = round(starter.combined_score - b.combined_score, 1)
        else:
            # Partial backup mapping if squad has fewer than 22 players
            for starter in best_xi:
                dropoff_by_slot[starter.slot_id] = 0.0

        unfit = [a for a in best_xi if a.fitness_alert]
        if unfit:
            best_warnings = best_warnings + [
                "Matchday Readiness: " + ", ".join(a.player.name.split()[-1] for a in unfit)
                + " start below full sharpness / freshness."]
        instructions = self.instructions_gen.generate(best_xi, tactical_style, best_warnings, matchup=matchup)
        return LineupResult(
            formation_name=best_formation.name,
            tactical_style=tactical_style,
            big_match_mode=big_match_mode,
            best_xi=best_xi,
            backup_xi=backup_xi,
            team_synergy_score=best_score,
            synergy_warnings=best_warnings,
            dropoff_by_slot=dropoff_by_slot,
            instructions=instructions,
            scoring_mode=scoring_mode,
            matchup=matchup,
            factor_in_fitness=factor_in_fitness,
            formation_ranking=ranking,
            excluded_count=len(squad) - len(pool),
        )

    # ------------------------------------------------------------------ "Why this XI?"
    def _slot_config(self, result: LineupResult, slot_id: str) -> Optional[FormationSlot]:
        form = self.formations.get(result.formation_name)
        return next((s for s in form.slots if s.slot_id == slot_id), None) if form else None

    def _slot_score(self, player: Player, slot: FormationSlot, result: LineupResult) -> float:
        return self._best_slot_assignment(player, slot, result.tactical_style, result.big_match_mode).combined_score

    @staticmethod
    def _with_attributes(target: Player, source: Player, group: Tuple[str, ...]) -> Player:
        """Copy of ``target`` that takes ``source``'s values for one attribute group (counterfactual)."""
        if group == (DRIVER_CA,):
            return replace(target, hidden=replace(target.hidden, ca=source.hidden.ca))
        if group == (DRIVER_CONSISTENCY,):
            return replace(target, hidden=replace(
                target.hidden, consistency=source.hidden.consistency,
                important_matches=source.hidden.important_matches, pressure=source.hidden.pressure))
        if group == (DRIVER_FAMILIARITY,):
            return replace(target, positions=list(source.positions), is_gk=source.is_gk,
                           position_familiarity=dict(source.position_familiarity))
        if group == (DRIVER_FITNESS,):
            return replace(target, match_sharpness=source.match_sharpness, fatigue=source.fatigue)
        if group == (DRIVER_FOOT,):
            return replace(target, preferred_foot=source.preferred_foot,
                           left_foot=source.left_foot, right_foot=source.right_foot)
        values = {a: source.visible.get(a) for a in group}
        return replace(target, visible=replace(target.visible, **values))

    def _driver_groups(self, slot: FormationSlot) -> List[Tuple[str, ...]]:
        attrs: Set[str] = set()
        for r in slot.ip_roles:
            attrs |= set(self.evaluator.attribute_weights(self.evaluator.ip_roles[r], slot.position))
        for r in slot.oop_roles:
            attrs |= set(self.evaluator.attribute_weights(self.evaluator.oop_roles[r], slot.position))
        # Transition load uses these physicals too.
        attrs |= {"stamina", "work_rate", "pace", "natural_fitness"}
        attrs &= set(PlayerVisibleAttributes.__dataclass_fields__)
        groups: List[Tuple[str, ...]] = []
        for combo in COMBINED_ATTRIBUTE_GROUPS:
            if attrs & set(combo):
                groups.append(combo)
                attrs -= set(combo)
        groups += [(a,) for a in sorted(attrs)]
        groups += [(DRIVER_CA,), (DRIVER_CONSISTENCY,), (DRIVER_FAMILIARITY,), (DRIVER_FITNESS,), (DRIVER_FOOT,)]
        return groups

    def compare_players(self, winner: Player, runner_up: Player, slot: FormationSlot,
                        result: LineupResult, limit: int = 3) -> List[ScoreDriver]:
        """Score points the runner-up would gain from each of the winner's attribute groups (largest first).

        Positive deltas favour the winner; the strongest negative one (where the runner-up is better) is
        appended so the comparison stays honest.
        """
        base = self._slot_score(runner_up, slot, result)
        drivers: List[ScoreDriver] = []
        for group in self._driver_groups(slot):
            delta = round(self._slot_score(self._with_attributes(runner_up, winner, group), slot, result) - base, 1)
            if abs(delta) >= MIN_DRIVER_POINTS:
                drivers.append(ScoreDriver(group, delta))
        pros = sorted((d for d in drivers if d.delta > 0), key=lambda d: -d.delta)[:limit]
        cons = sorted((d for d in drivers if d.delta < 0), key=lambda d: d.delta)[:1]
        return pros + cons

    def explain_slot(self, result: LineupResult, slot: AssignedSlot, squad: List[Player],
                     lineup: Optional[List[AssignedSlot]] = None) -> SlotExplanation:
        """'Why this XI?': top contributing attributes and the runner-up comparison for one slot.

        The runner-up is the best available player outside ``lineup`` (default: the Best XI) for this
        slot; with no one left outside, the best other player in the squad.
        """
        self.evaluator.configure(result.scoring_mode, result.matchup, result.factor_in_fitness)
        contributions = self.evaluator.attribute_contributions(
            slot.player, slot.ip_role, slot.oop_role, slot.position, IP_WEIGHT)[:5]
        explanation = SlotExplanation(slot.slot_id, slot.player, slot.combined_score, contributions)
        cfg = self._slot_config(result, slot.slot_id)
        if cfg is None:
            return explanation
        lineup = lineup if lineup is not None else result.best_xi
        in_lineup = {a.player.player_id for a in lineup}
        pool = [p for p in eligible_players(squad) if p.player_id != slot.player.player_id]
        candidates = [p for p in pool if p.player_id not in in_lineup] or pool
        if not candidates:
            return explanation
        scored = sorted(((self._slot_score(p, cfg, result), p) for p in candidates), key=lambda sp: -sp[0])
        runner_score, runner = scored[0]
        explanation.runner_up = runner
        explanation.runner_up_score = runner_score
        explanation.drivers = self.compare_players(slot.player, runner, cfg, result)
        return explanation
