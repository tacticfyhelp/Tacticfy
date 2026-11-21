"""Converts engine results into JSON-safe dicts for the browser UI.

Everything the UI shows is either an FM27 name (sent as-is, never translated) or a translation key
plus arguments that the browser renders in English or Hebrew.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.advisor.squad_classifier import has_real_finances
from src.engine.bench_optimizer import BenchPlan
from src.engine.instructions_gen import InstructionsGenerator
from src.engine.training_advisor import TrainingRecommendation
from src.models.player import Player
from src.models.tactics import AssignedSlot, LineupResult, PlayerClassification, WeakestLinkReport

# Fallback only (slots without display coords): keep L/R slots off the centre line.
_CENTER_SPLIT = 14.0
_PHASE_SUBHEADERS = {"Build-Up", "Progression", "Final Third", "High Press", "Mid Block", "Low Block"}

SUB_KIND_EN = {"chase_goal": "Chase a Goal", "protect_lead": "Protect a Lead", "fatigue": "Fresh Legs"}


def category_key(category: str) -> str:
    """Classifier category label -> colour / bucket key."""
    if "Core" in category:
        return "core"
    if "Rotation" in category:
        return "rotation"
    if "Loan" in category:
        return "loan"
    if "False Potential" in category:
        return "sell_high"
    return "offload"


def _r(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def player_json(p: Player, show_wage: bool = True) -> Dict[str, Any]:
    h = p.hidden
    return {
        "id": p.player_id,
        "name": p.name,
        "surname": p.name.split()[-1] if p.name.strip() else "",
        "age": p.age,
        "positions": list(p.positions),
        "is_gk": p.is_gk,
        "locked": p.locked_starter,
        "ca": h.ca,
        "pa": h.pa,
        "headroom": p.pa_ca_delta,
        "prof": h.professionalism,
        "amb": h.ambition,
        "imp": h.important_matches,
        "pres": h.pressure,
        "cons": h.consistency,
        "inj": h.injury_proneness,
        "wage": p.wage_weekly if show_wage else None,
    }


def _display_xy(slot: AssignedSlot, phase: str) -> Tuple[float, float]:
    shape = slot.ip_display if phase == "IP" else slot.oop_display
    if shape is not None:
        return _r(shape[0]), _r(shape[1])
    x, y = slot.ip_coords if phase == "IP" else slot.oop_coords
    if slot.side == "L":
        x = min(x, 50.0 - _CENTER_SPLIT)
    elif slot.side == "R":
        x = max(x, 50.0 + _CENTER_SPLIT)
    return _r(x), _r(y)


def slot_json(a: AssignedSlot) -> Dict[str, Any]:
    return {
        "slot_id": a.slot_id,
        "position": a.position,
        "side": a.side,
        "player_id": a.player.player_id,
        "name": a.player.name,
        "surname": a.player.name.split()[-1] if a.player.name.strip() else a.slot_id,
        "ip_role": a.ip_role,
        "ip_score": _r(a.ip_score),
        "oop_role": a.oop_role,
        "oop_score": _r(a.oop_score),
        "combined": _r(a.combined_score),
        "transition_distance": _r(a.transition_distance),
        "transition_alert": a.transition_alert,
        "instructions": list(a.individual_instructions),
        "ip_xy": _display_xy(a, "IP"),
        "oop_xy": _display_xy(a, "OOP"),
    }


def _phase(tile: str) -> str:
    phase = InstructionsGenerator.phase_of(tile).split(" - ")[-1]
    return phase if phase in _PHASE_SUBHEADERS else ""


def _tiles(items: Dict[str, str]) -> List[Dict[str, str]]:
    return [{"tile": k, "value": v, "phase": _phase(k)} for k, v in items.items()]


def lineup_json(result: LineupResult) -> Dict[str, Any]:
    ins = result.instructions
    return {
        "formation": result.formation_name,
        "style": result.tactical_style,
        "important": result.big_match_mode,
        "synergy": _r(result.team_synergy_score),
        "warnings": list(result.synergy_warnings),
        "dropoff": {k: _r(v) for k, v in result.dropoff_by_slot.items()},
        "best_xi": [slot_json(a) for a in result.best_xi],
        "second_xi": [slot_json(a) for a in result.backup_xi],
        "instructions": {
            "mentality": ins.mentality,
            "in_possession": _tiles(ins.in_possession),
            "in_transition": _tiles(ins.in_transition),
            "out_of_possession": _tiles(ins.out_of_possession),
            "notes": list(ins.tactical_notes),
        },
    }


def bench_json(plan: Optional[BenchPlan]) -> Optional[Dict[str, Any]]:
    if plan is None:
        return None
    return {
        "size": plan.size,
        "bench": [
            {
                "player_id": b.player.player_id,
                "name": b.player.name,
                "positions": list(b.player.positions),
                "role": b.bench_role,
                "covered_slots": list(b.covered_slots),
                "covered_positions": list(b.covered_positions),
                "best_slot": b.best_cover_slot,
                "best_score": _r(b.best_cover_score),
                "impact": _r(b.impact),
            }
            for b in plan.bench
        ],
        "uncovered": list(plan.uncovered_slots),
        "scenarios": [
            {
                "kind": s.kind,
                "minute": s.minute,
                "on": s.player_on.name,
                "off": s.player_off.name,
                "slot_id": s.slot_id,
                "ip_role": s.ip_role,
                "oop_role": s.oop_role,
                "reason_key": s.reason_key,
                "reason_args": s.reason_args,
            }
            for s in plan.scenarios
        ],
    }


def training_json(rec: TrainingRecommendation) -> Dict[str, Any]:
    return {
        "player_id": rec.player.player_id,
        "name": rec.player.name,
        "role_focus": rec.role_focus,
        "role_source": rec.role_source,
        "additional_focus": rec.additional_focus,
        "intensity": rec.intensity,
        "reason_key": rec.reason_key,
        "reason_args": rec.reason_args,
        "focus_attributes": list(rec.focus_attributes),
    }


def classified_json(c: PlayerClassification, show_wage: bool) -> Dict[str, Any]:
    return {
        "player": player_json(c.player, show_wage),
        "category": c.category,
        "category_key": category_key(c.category),
        "best_ip_role": c.best_ip_role,
        "best_ip_score": _r(c.best_ip_score),
        "best_oop_role": c.best_oop_role,
        "best_oop_score": _r(c.best_oop_score),
        "reasons": list(c.reasons),
    }


def weakest_json(w: WeakestLinkReport) -> Dict[str, Any]:
    return {
        "slot_id": w.weakest_slot_id,
        "player_name": w.weakest_player_name,
        "score": _r(w.weakest_slot_score),
        "dropoff_slot": w.steepest_dropoff_slot,
        "dropoff_delta": _r(w.steepest_dropoff_delta),
        "target_role": w.target_role,
        "target_position": w.target_position,
        "minimum_attributes": dict(w.minimum_attributes),
    }


def analysis_json(
    squad: List[Player],
    result: LineupResult,
    classified: List[PlayerClassification],
    weakest: WeakestLinkReport,
    training: List[TrainingRecommendation],
    bench: Optional[BenchPlan],
) -> Dict[str, Any]:
    show_wage = has_real_finances(squad)
    return {
        "lineup": lineup_json(result),
        "bench": bench_json(bench),
        "squad": [classified_json(c, show_wage) for c in classified],
        "show_wage": show_wage,
        "weakest": weakest_json(weakest),
        "training": [training_json(r) for r in training],
        "plan_text": match_plan_text(result, bench),
    }


def match_plan_text(result: LineupResult, plan: Optional[BenchPlan] = None) -> str:
    """Plain-text match plan for the clipboard, always in FM27 English so it matches the game."""
    ins = result.instructions
    lines = [
        f"FM27 Match Plan - {result.formation_name} | {result.tactical_style}"
        f"{' | Important Match' if result.big_match_mode else ''}",
        f"Team Synergy: {result.team_synergy_score:.1f}  |  Mentality: {ins.mentality}",
        "",
        "BEST XI (In Possession role / Out of Possession role)",
    ]
    for a in result.best_xi:
        lines.append(f"  {a.slot_id:<5} {a.player.name:<26} {a.ip_role} / {a.oop_role}  ({a.combined_score:.1f})")
        if a.individual_instructions:
            lines.append(f"        PI: {', '.join(a.individual_instructions)}")
    for title, items in (
        ("IN POSSESSION", ins.in_possession),
        ("IN TRANSITION", ins.in_transition),
        ("OUT OF POSSESSION", ins.out_of_possession),
    ):
        lines += ["", title]
        current_phase = None
        for k, v in items.items():
            phase = _phase(k)
            if phase and phase != current_phase:
                lines.append(f"  [{phase}]")
            current_phase = phase or current_phase
            lines.append(f"  {k}: {v}")
    if ins.tactical_notes:
        lines += ["", "NOTES"] + [f"  - {n}" for n in ins.tactical_notes]
    if plan is not None and plan.bench:
        lines += ["", f"MATCHDAY BENCH ({len(plan.bench)} subs)"]
        for b in plan.bench:
            lines.append(f"  {b.player.name:<26} {'/'.join(b.player.positions):<12} covers {', '.join(b.covered_positions)}")
        if plan.scenarios:
            lines += ["", "PLANNED SUBSTITUTIONS"]
            for s in plan.scenarios:
                lines.append(f"  {s.minute} {SUB_KIND_EN.get(s.kind, s.kind)}: {s.player_on.name} ON for "
                             f"{s.player_off.name} ({s.slot_id}) as {s.ip_role} / {s.oop_role}")
    return "\n".join(lines)
