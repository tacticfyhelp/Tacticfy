"""Individual training recommendations (Role Focus, Additional Focus, Training Intensity).

For every player the advisor picks:
  * Role Focus - the FM27 In Possession role the player is assigned to in the Best XI / Second XI, or
    his strongest natural role when he is not in either XI. Role names stay in official FM27 English.
  * Additional Focus - the FM27 additional-focus group that closes the biggest weighted gap between
    the player's attributes and the role's highest-weighted (primary / secondary) attributes.
  * Training Intensity - Double / Normal / Half, from Age, PA-CA headroom, Professionalism,
    Determination and Injury Proneness.
  * A one-line reason, returned as a translation key + arguments so the UI can render it in EN or HE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.engine.role_evaluator import RoleEvaluator
from src.models.player import Player
from src.models.tactics import LineupResult

# Additional-focus identifiers (English, as shown in FM27) -> attributes they develop.
OUTFIELD_FOCUS_ATTRIBUTES: Dict[str, Tuple[str, ...]] = {
    "Quickness": ("acceleration", "pace", "agility"),
    "Endurance": ("stamina", "natural_fitness", "work_rate"),
    "Passing": ("passing", "vision", "technique"),
    "Final Third": ("finishing", "off_the_ball", "composure", "long_shots"),
    "Defensive Positioning": ("positioning", "marking", "anticipation", "concentration", "tackling"),
    "Aerial": ("heading", "jumping_reach", "strength"),
    "Ball Control": ("first_touch", "technique", "dribbling"),
}
GOALKEEPER_FOCUS_ATTRIBUTES: Dict[str, Tuple[str, ...]] = {
    "Shot Stopping": ("reflexes", "one_on_ones", "handling"),
    "Aerial": ("aerial_reach", "command_of_area", "jumping_reach", "punching"),
    "Distribution": ("kicking", "throwing", "passing"),
    "Quickness": ("acceleration", "agility", "rushing_out"),
}
NO_FOCUS = "None"

DOUBLE = "Double Intensity"
NORMAL = "Normal"
HALF = "Half Intensity"
INTENSITIES = (DOUBLE, NORMAL, HALF)

ROLE_SOURCE_BEST_XI = "best_xi"
ROLE_SOURCE_SECOND_XI = "second_xi"
ROLE_SOURCE_NATURAL = "natural"

PRIMARY_WEIGHT = 3.0
SECONDARY_WEIGHT = 1.5
TARGET_LEVEL = 16          # attribute level the role should reach before a gap stops counting
MIN_FOCUS_GAP = 4.0        # weighted gap below which no additional focus is worth it
CEILING_HEADROOM = 2       # PA - CA at or below this: the player can no longer grow


@dataclass
class TrainingRecommendation:
    """Individual training plan for one player."""

    player: Player
    role_focus: str
    role_source: str
    additional_focus: str
    intensity: str
    reason_key: str
    reason_args: Dict[str, object] = field(default_factory=dict)
    focus_attributes: List[str] = field(default_factory=list)  # weakest role attributes the focus targets


class TrainingAdvisor:
    """Builds an individual training recommendation for every player in the squad."""

    def __init__(self, evaluator: RoleEvaluator) -> None:
        self.evaluator = evaluator

    # ------------------------------------------------------------------ role
    def _assigned_roles(self, lineup: Optional[LineupResult]) -> Dict[int, Tuple[str, str]]:
        roles: Dict[int, Tuple[str, str]] = {}
        if lineup is None:
            return roles
        for slot in lineup.backup_xi:
            roles[slot.player.player_id] = (slot.ip_role, ROLE_SOURCE_SECOND_XI)
        for slot in lineup.best_xi:  # Best XI wins if a player somehow appears in both
            roles[slot.player.player_id] = (slot.ip_role, ROLE_SOURCE_BEST_XI)
        return roles

    def role_for(self, player: Player, lineup: Optional[LineupResult] = None) -> Tuple[str, str]:
        """(FM27 role name, role source) used as the player's Role Focus."""
        assigned = self._assigned_roles(lineup).get(player.player_id)
        if assigned:
            return assigned
        role, _ = self.evaluator.best_overall_ip_role(player)
        return role, ROLE_SOURCE_NATURAL

    # ------------------------------------------------------------------ additional focus
    def focus_gaps(self, player: Player, role_name: str) -> Dict[str, Tuple[float, List[str]]]:
        """Weighted role-attribute gap closed by each additional focus (focus -> (gap, attributes))."""
        role = self.evaluator.ip_roles.get(role_name)
        if role is None:
            return {}
        weights: Dict[str, float] = {a: SECONDARY_WEIGHT for a in role.secondary}
        weights.update({a: PRIMARY_WEIGHT for a in role.primary})
        groups = GOALKEEPER_FOCUS_ATTRIBUTES if player.is_gk else OUTFIELD_FOCUS_ATTRIBUTES
        out: Dict[str, Tuple[float, List[str]]] = {}
        for focus, attrs in groups.items():
            gap, weak = 0.0, []
            for attr in attrs:
                w = weights.get(attr)
                if not w:
                    continue
                missing = max(0, TARGET_LEVEL - player.visible.get(attr, 10))
                if missing:
                    gap += missing * w
                    weak.append(attr)
            weak.sort(key=lambda a: player.visible.get(a, 10))
            out[focus] = (round(gap, 1), weak)
        return out

    # ------------------------------------------------------------------ intensity
    @staticmethod
    def intensity_for(player: Player) -> Tuple[str, str, Dict[str, object]]:
        """(intensity, reason_key, reason_args) from age, headroom, mentality and injury risk."""
        h = player.hidden
        det = player.visible.determination
        headroom = player.pa_ca_delta
        if h.injury_proneness >= 15:
            return HALF, "training.reason.injury_risk", {"inj": h.injury_proneness}
        if player.age >= 32:
            return HALF, "training.reason.veteran", {"age": player.age}
        if (
            player.age <= 23
            and headroom >= 10
            and h.professionalism >= 12
            and det >= 12
            and h.injury_proneness <= 12
        ):
            return DOUBLE, "training.reason.develop", {
                "age": player.age, "headroom": headroom, "prof": h.professionalism, "det": det,
            }
        if player.age <= 23 and headroom >= 10:
            return NORMAL, "training.reason.mentality_limits", {
                "headroom": headroom, "prof": h.professionalism, "det": det,
            }
        return NORMAL, "", {}

    # ------------------------------------------------------------------ public
    def recommend_player(self, player: Player, lineup: Optional[LineupResult] = None) -> TrainingRecommendation:
        role, source = self.role_for(player, lineup)
        intensity, reason_key, args = self.intensity_for(player)

        gaps = self.focus_gaps(player, role)
        focus, weak = NO_FOCUS, []
        if gaps:
            best_focus, (best_gap, best_weak) = max(gaps.items(), key=lambda kv: kv[1][0])
            if best_gap >= MIN_FOCUS_GAP and player.pa_ca_delta > CEILING_HEADROOM:
                focus, weak = best_focus, best_weak

        if not reason_key:  # no intensity-driven reason: explain the focus choice instead
            if focus != NO_FOCUS:
                reason_key = "training.reason.focus_gap"
                args = {"attrs": weak[:2], "role": role}
            elif player.pa_ca_delta <= CEILING_HEADROOM:
                reason_key = "training.reason.ceiling"
                args = {"ca": player.hidden.ca, "pa": player.hidden.pa}
            else:
                reason_key = "training.reason.complete"
                args = {"role": role}
        else:
            args = {**args, "attrs": weak[:2], "role": role}

        return TrainingRecommendation(
            player=player,
            role_focus=role,
            role_source=source,
            additional_focus=focus,
            intensity=intensity,
            reason_key=reason_key,
            reason_args=args,
            focus_attributes=weak,
        )

    def recommend(self, squad: List[Player], lineup: Optional[LineupResult] = None) -> List[TrainingRecommendation]:
        """Recommendations for the whole squad, Best XI first, then Second XI, then the rest (by CA)."""
        order = {ROLE_SOURCE_BEST_XI: 0, ROLE_SOURCE_SECOND_XI: 1, ROLE_SOURCE_NATURAL: 2}
        recs = [self.recommend_player(p, lineup) for p in squad]
        recs.sort(key=lambda r: (order[r.role_source], -r.player.hidden.ca))
        return recs
