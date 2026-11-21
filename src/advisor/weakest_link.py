"""Identifies the weakest starter / steepest depth drop-off and builds a scouting filter."""

from typing import Dict

from src.engine.role_evaluator import RoleEvaluator
from src.models.tactics import LineupResult, WeakestLinkReport


class WeakestLinkAnalyzer:
    """Generates a concrete transfer target attribute profile to upgrade the Best XI."""

    def __init__(self, evaluator: RoleEvaluator) -> None:
        self.evaluator = evaluator

    def analyze(self, lineup: LineupResult) -> WeakestLinkReport:
        """Find weakest starting slot and steepest Backup XI drop-off."""
        weakest_slot = min(lineup.best_xi, key=lambda a: a.combined_score)

        steepest_slot = weakest_slot.slot_id
        steepest_delta = 0.0
        if lineup.dropoff_by_slot:
            steepest_slot = max(lineup.dropoff_by_slot, key=lambda k: lineup.dropoff_by_slot[k])
            steepest_delta = lineup.dropoff_by_slot[steepest_slot]

        ip_def = self.evaluator.ip_roles[weakest_slot.ip_role]
        oop_def = self.evaluator.oop_roles[weakest_slot.oop_role]

        min_attrs: Dict[str, int] = {}
        for attr in ip_def.primary[:5]:
            current_val = weakest_slot.player.visible.get(attr, 10)
            min_attrs[attr] = min(17, max(13, current_val + 2))
        for attr in oop_def.primary[:3]:
            if attr not in min_attrs:
                current_val = weakest_slot.player.visible.get(attr, 10)
                min_attrs[attr] = min(16, max(12, current_val + 2))
        min_attrs["important_matches"] = 12
        min_attrs["professionalism"] = 12

        depth_txt = (
            f"Steepest squad depth drop-off is at {steepest_slot} (-{steepest_delta:.1f} pts)."
            if lineup.backup_xi
            else "No full Second XI available, so depth drop-off cannot be measured."
        )
        summary = (
            f"Priority Upgrade: {weakest_slot.slot_id} ({weakest_slot.player.name}, "
            f"Score {weakest_slot.combined_score:.1f} as {weakest_slot.ip_role}). {depth_txt}"
        )

        return WeakestLinkReport(
            weakest_slot_id=weakest_slot.slot_id,
            weakest_player_name=weakest_slot.player.name,
            weakest_slot_score=weakest_slot.combined_score,
            steepest_dropoff_slot=steepest_slot,
            steepest_dropoff_delta=steepest_delta,
            target_role=weakest_slot.ip_role,
            target_position=weakest_slot.position,
            minimum_attributes=min_attrs,
            summary=summary,
        )
