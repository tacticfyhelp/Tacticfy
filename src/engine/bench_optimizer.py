"""Recommended Matchday Bench and suggested in-game substitutions.

Bench selection (players NOT in the Best XI):
  1. One backup goalkeeper (best GK by IP/OOP score in the starting keeper's roles).
  2. One cover player per line (defence / midfield / attack) when the pool allows.
  3. Remaining seats filled greedily by marginal coverage gain across the 10 outfield slots, where
     each slot is weighted by its starter's fatigue risk (Stamina / Natural Fitness) and each
     candidate gets a utility bonus for Versatility, Important Matches and impact attributes
     (Pace / Acceleration / Dribbling).

Substitution scenarios: Chase a Goal (more pace/dribbling/finishing up front), Protect a Lead
(fresh defensive legs for a tiring attacker) and a like-for-like fatigue change.
Reasons are translation keys + arguments; role names stay in official FM27 English.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.engine.role_evaluator import POSITION_ROLE_GROUPS, RoleEvaluator
from src.models.player import Player
from src.models.tactics import AssignedSlot, LineupResult

DEFAULT_BENCH_SIZE = 9
SUPPORTED_BENCH_SIZES = (7, 9)

DEFENCE = {"DL", "DC", "DR", "WBL", "WBR"}
MIDFIELD = {"DM", "ML", "MC", "MR"}
ATTACK = {"AML", "AMC", "AMR", "ST"}
LINES = (("defence", DEFENCE), ("midfield", MIDFIELD), ("attack", ATTACK))
ATTACKING_SLOTS = ATTACK | {"ML", "MR", "MC"}

COVER_FAMILIARITY = 0.82   # Player.familiarity_for() multiplier: "Competent" or better
IP_WEIGHT, OOP_WEIGHT = 0.58, 0.42  # same phase weighting as SynergyOptimizer

SCENARIO_CHASE = "chase_goal"
SCENARIO_PROTECT = "protect_lead"
SCENARIO_FATIGUE = "fatigue"
SCENARIO_MINUTES = {SCENARIO_CHASE: "60'–70'", SCENARIO_FATIGUE: "60'–75'", SCENARIO_PROTECT: "70'–80'"}


@dataclass
class BenchPlayer:
    """One recommended substitute."""

    player: Player
    bench_role: str                      # "backup_gk" / "defence" / "midfield" / "attack" / "utility"
    covered_slots: List[str] = field(default_factory=list)    # Best XI slot ids he can cover
    covered_positions: List[str] = field(default_factory=list)
    best_cover_slot: str = ""
    best_cover_score: float = 0.0
    impact: float = 0.0


@dataclass
class SubScenario:
    """One planned in-game substitution."""

    kind: str
    minute: str
    player_off: Player
    player_on: Player
    slot_id: str
    position: str
    ip_role: str
    oop_role: str
    reason_key: str
    reason_args: Dict[str, object] = field(default_factory=dict)


@dataclass
class BenchPlan:
    """Matchday bench + substitution plan."""

    size: int
    bench: List[BenchPlayer]
    uncovered_slots: List[str]
    scenarios: List[SubScenario]


def impact_score(p: Player) -> float:
    """0-20 attacking impact off the bench (Pace / Acceleration / Dribbling, plus Finishing / Flair)."""
    v = p.visible
    return round(v.pace * 0.28 + v.acceleration * 0.28 + v.dribbling * 0.22 + v.finishing * 0.12 + v.flair * 0.10, 2)


def defensive_score(p: Player) -> float:
    """0-20 ability to see out a lead."""
    v = p.visible
    return round(
        v.tackling * 0.22 + v.marking * 0.20 + v.positioning * 0.22 + v.work_rate * 0.14
        + v.concentration * 0.12 + v.stamina * 0.10, 2
    )


def late_game_factor(p: Player) -> float:
    """Share of a starter's output left at 60'-75' (fresh substitutes count as 1.0)."""
    v = p.visible
    return max(0.6, 1.0 - (0.10 + max(0, 16 - v.stamina) * 0.02 + max(0, 14 - v.natural_fitness) * 0.01))


def fatigue_risk(p: Player) -> float:
    """0..~1.3: how likely a starter is to need replacing (low Stamina / Natural Fitness)."""
    v = p.visible
    return max(0.0, (14 - v.stamina) / 10.0) + max(0.0, (14 - v.natural_fitness) / 20.0)


class BenchOptimizer:
    """Selects the matchday bench and plans substitutions for a solved lineup."""

    def __init__(self, evaluator: RoleEvaluator) -> None:
        self.evaluator = evaluator

    def cover_score(self, player: Player, slot: AssignedSlot) -> float:
        """Player's combined IP/OOP score in the starter's exact roles, 0 when he cannot play there."""
        if player.familiarity_for(slot.position) < COVER_FAMILIARITY:
            return 0.0
        ip = self.evaluator.score_ip_role(player, slot.ip_role, slot.position, side=slot.side)
        oop = self.evaluator.score_oop_role(player, slot.oop_role, slot.position)
        return round(ip * IP_WEIGHT + oop * OOP_WEIGHT, 1)

    @staticmethod
    def _utility(p: Player) -> float:
        h = p.hidden
        return h.versatility / 20.0 * 6.0 + h.important_matches / 20.0 * 4.0 + impact_score(p) / 20.0 * 4.0

    # ------------------------------------------------------------------ bench
    def select_bench(self, squad: List[Player], lineup: LineupResult, size: int = DEFAULT_BENCH_SIZE) -> BenchPlan:
        if size < 1:
            raise ValueError("Bench size must be at least 1.")
        starter_ids = {a.player.player_id for a in lineup.best_xi}
        pool = [p for p in squad if p.player_id not in starter_ids]
        gk_slots = [a for a in lineup.best_xi if a.position == "GK"]
        outfield_slots = [a for a in lineup.best_xi if a.position != "GK"]

        cover: Dict[int, Dict[str, float]] = {
            p.player_id: {s.slot_id: self.cover_score(p, s) for s in outfield_slots} for p in pool if not p.is_gk
        }
        need = {s.slot_id: 1.0 + fatigue_risk(s.player) for s in outfield_slots}
        chosen: List[BenchPlayer] = []
        chosen_ids: set = set()

        # 1. Backup goalkeeper
        keepers = [p for p in pool if p.is_gk]
        if keepers and gk_slots:
            gk_slot = gk_slots[0]
            ranked = sorted(
                keepers,
                key=lambda p: -(self.evaluator.score_ip_role(p, gk_slot.ip_role, "GK") * IP_WEIGHT
                                + self.evaluator.score_oop_role(p, gk_slot.oop_role, "GK") * OOP_WEIGHT),
            )
            gk = ranked[0]
            chosen.append(BenchPlayer(gk, "backup_gk", [gk_slot.slot_id], ["GK"], gk_slot.slot_id,
                                      self.cover_score(gk, gk_slot), impact_score(gk)))
            chosen_ids.add(gk.player_id)

        best_cover = {s.slot_id: 0.0 for s in outfield_slots}

        def gain(p: Player) -> float:
            c = cover[p.player_id]
            g = sum(need[sid] * max(0.0, c[sid] - best_cover[sid]) for sid in best_cover)
            return g + self._utility(p) if g > 0 else self._utility(p) * 0.25

        def take(p: Player, role: str) -> None:
            c = cover[p.player_id]
            slots = [s for s in outfield_slots if c[s.slot_id] > 0]
            best = max(slots, key=lambda s: c[s.slot_id]) if slots else None
            chosen.append(BenchPlayer(
                p, role,
                covered_slots=[s.slot_id for s in slots],
                covered_positions=sorted({s.position for s in slots}, key=_position_order),
                best_cover_slot=best.slot_id if best else "",
                best_cover_score=c[best.slot_id] if best else 0.0,
                impact=impact_score(p),
            ))
            chosen_ids.add(p.player_id)
            for sid, val in c.items():
                best_cover[sid] = max(best_cover[sid], val)

        outfield_pool = [p for p in pool if not p.is_gk]
        # 2. One cover player per line
        for line, positions in LINES:
            if len(chosen) >= size:
                break
            line_slots = [s.slot_id for s in outfield_slots if s.position in positions]
            candidates = [p for p in outfield_pool if p.player_id not in chosen_ids
                          and any(cover[p.player_id][sid] > 0 for sid in line_slots)]
            if line_slots and candidates:
                pick = max(candidates, key=lambda p: (
                    sum(need[sid] * cover[p.player_id][sid] for sid in line_slots) / len(line_slots) + self._utility(p)
                ))
                take(pick, line)

        # 3. Greedy fill
        while len(chosen) < size:
            candidates = [p for p in outfield_pool if p.player_id not in chosen_ids]
            if not candidates:
                break
            take(max(candidates, key=gain), "utility")

        uncovered = [s.slot_id for s in outfield_slots if best_cover[s.slot_id] <= 0]
        if gk_slots and not any(b.bench_role == "backup_gk" for b in chosen):
            uncovered.insert(0, gk_slots[0].slot_id)
        scenarios = self.plan_substitutions(lineup, chosen)
        return BenchPlan(size=size, bench=chosen, uncovered_slots=uncovered, scenarios=scenarios)

    # ------------------------------------------------------------------ substitutions
    def plan_substitutions(self, lineup: LineupResult, bench: List[BenchPlayer]) -> List[SubScenario]:
        outfield_bench = [b.player for b in bench if b.bench_role != "backup_gk"]
        starters = [a for a in lineup.best_xi if a.position != "GK"]
        if not outfield_bench or not starters:
            return []
        scenarios: List[SubScenario] = []
        used_on: set = set()

        def tired_impact(p: Player) -> float:
            return impact_score(p) * late_game_factor(p)

        def tired_defence(p: Player) -> float:
            return defensive_score(p) * late_game_factor(p)

        def best_swap(slots: List[AssignedSlot], value) -> Optional[tuple]:
            best = None
            for s in slots:
                for b in outfield_bench:
                    if b.player_id in used_on:
                        continue
                    c = self.cover_score(b, s)
                    if c <= 0:
                        continue
                    v = value(b, s, c)
                    if best is None or v > best[0]:
                        best = (v, b, s, c)
            return best

        # Chase a Goal: biggest attacking-impact upgrade in an attacking / midfield slot.
        chase = best_swap(
            [s for s in starters if s.position in ATTACKING_SLOTS],
            lambda b, s, c: (impact_score(b) - tired_impact(s.player)) * 2.0 + c / 25.0,
        )
        if chase and impact_score(chase[1]) > tired_impact(chase[2].player):
            _, b, s, _ = chase
            scenarios.append(self._scenario(SCENARIO_CHASE, s, b, "subs.reason.chase", {
                "on_impact": round(impact_score(b), 1), "off_impact": round(tired_impact(s.player), 1),
                "pace": b.visible.pace, "dribbling": b.visible.dribbling,
            }))
            used_on.add(b.player_id)

        # Protect a Lead: fresh defensive legs for the least defensive attacker / wide player.
        protect = best_swap(
            [s for s in starters if s.position in ATTACKING_SLOTS],
            lambda b, s, c: (defensive_score(b) - tired_defence(s.player)) * 2.0 + c / 25.0,
        )
        if protect and defensive_score(protect[1]) > tired_defence(protect[2].player):
            _, b, s, _ = protect
            scenarios.append(self._scenario(SCENARIO_PROTECT, s, b, "subs.reason.protect", {
                "on_def": round(defensive_score(b), 1), "off_def": round(tired_defence(s.player), 1),
                "work_rate": b.visible.work_rate, "tackling": b.visible.tackling,
            }))
            used_on.add(b.player_id)

        # Like-for-like fatigue change for the starter most likely to tire (lowest Stamina on ties).
        tired = sorted(starters, key=lambda s: (-fatigue_risk(s.player), s.player.visible.stamina))
        if tired:
            swap = best_swap([tired[0]], lambda b, s, c: c)
            if swap:
                _, b, s, _ = swap
                scenarios.append(self._scenario(SCENARIO_FATIGUE, s, b, "subs.reason.fatigue", {
                    "stamina": s.player.visible.stamina, "fitness": s.player.visible.natural_fitness,
                }))
        return scenarios

    def _roles_for(self, player: Player, slot: AssignedSlot, kind: str) -> tuple:
        """Incoming player's best FM27 IP / OOP role at the slot position (starter's roles for like-for-like)."""
        if kind == SCENARIO_FATIGUE:
            return slot.ip_role, slot.oop_role
        groups = POSITION_ROLE_GROUPS.get(slot.position, set())
        ip_roles = [n for n, r in self.evaluator.ip_roles.items() if r.slot_group in groups] or [slot.ip_role]
        oop_roles = [n for n, r in self.evaluator.oop_roles.items() if r.slot_group in groups] or [slot.oop_role]
        ip = max(ip_roles, key=lambda n: self.evaluator.score_ip_role(player, n, slot.position, side=slot.side))
        oop = max(oop_roles, key=lambda n: self.evaluator.score_oop_role(player, n, slot.position))
        return ip, oop

    def _scenario(self, kind: str, slot: AssignedSlot, on: Player, key: str, args: Dict[str, object]) -> SubScenario:
        ip_role, oop_role = self._roles_for(on, slot, kind)
        return SubScenario(
            kind=kind, minute=SCENARIO_MINUTES[kind], player_off=slot.player, player_on=on,
            slot_id=slot.slot_id, position=slot.position, ip_role=ip_role, oop_role=oop_role,
            reason_key=key, reason_args=args,
        )


_POS_ORDER = ["GK", "DL", "DC", "DR", "WBL", "WBR", "DM", "ML", "MC", "MR", "AML", "AMC", "AMR", "ST"]


def _position_order(pos: str) -> int:
    return _POS_ORDER.index(pos) if pos in _POS_ORDER else len(_POS_ORDER)
