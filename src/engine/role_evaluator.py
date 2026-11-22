"""Evaluates FM27 players for both In Possession and Out of Possession roles."""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.models.player import Player
from src.models.tactics import (
    MATCHUP_AERIAL, MATCHUP_FAST_COUNTER, MATCHUP_FAVORITE, MATCHUP_NEUTRAL, MATCHUP_UNDERDOG, MATCHUPS,
    SCORING_FM_META, SCORING_MODES, AttributeContribution, RoleDefinition,
)


# FM27 In Possession roles that hug the touchline want the foot on the same side (left-footed on the left).
TOUCHLINE_ROLES = {"Winger", "Wide Forward", "Wide Midfielder", "Wing-Back", "Advanced Wing-Back", "Full-Back",
                   "Overlapping Centre-Back"}
# FM27 roles that cut inside with the ball want the opposite foot (right-footed on the left).
INVERTED_ROLES = {"Inside Forward", "Inside Winger"}

# FM27 Out of Possession role families, used for style emphasis (names from the game's RolesData).
AGGRESSIVE_OOP_PREFIXES = ("Pressing ", "Stopping ")
CONSERVATIVE_OOP_PREFIXES = ("Screening ", "Holding ", "Covering ", "Tracking ", "Dropping ")
OUTLET_OOP_MARKER = "Outlet"
LEFT_POSITIONS = {"DL", "WBL", "ML", "AML"}
RIGHT_POSITIONS = {"DR", "WBR", "MR", "AMR"}
# Role groups that make sense for each FM position (used for "best role" lookups).
POSITION_ROLE_GROUPS = {
    "GK": {"GK"},
    "DC": {"DC"},
    "DL": {"FB"}, "DR": {"FB"}, "WBL": {"FB"}, "WBR": {"FB"},
    "DM": {"DM"},
    "MC": {"CM"},
    "ML": {"W"}, "MR": {"W"},
    "AML": {"W"}, "AMR": {"W"},
    "AMC": {"AM"},
    "ST": {"ST"},
}


PRIMARY_WEIGHT, SECONDARY_WEIGHT = 3.0, 1.5

# FM Meta layer: attributes the FM match engine rewards far beyond their role weight (fast, physically
# dominant, mentally sharp players). Added on top of the role's own primary / secondary weights.
META_WEIGHTS_OUTFIELD: Dict[str, float] = {
    "pace": 1.6, "acceleration": 1.6, "jumping_reach": 0.9, "anticipation": 1.2, "concentration": 0.8,
    "dribbling": 0.8, "agility": 0.8, "balance": 0.6, "decisions": 1.1,
}
META_WEIGHTS_GK: Dict[str, float] = {"reflexes": 1.6, "agility": 1.2, "one_on_ones": 1.2, "aerial_reach": 1.0}

# Pitch line of an FM position, used by the Matchup layer.
POSITION_LINE = {
    "GK": "GK", "DC": "CB", "DL": "FB", "DR": "FB", "WBL": "FB", "WBR": "FB",
    "DM": "MID", "MC": "MID", "ML": "MID", "MR": "MID",
    "AML": "ATT", "AMR": "ATT", "AMC": "ATT", "ST": "ATT",
}
# Opponent matchup layer: extra attribute weight per pitch line.
MATCHUP_WEIGHTS: Dict[str, Dict[str, Dict[str, float]]] = {
    MATCHUP_FAST_COUNTER: {
        "CB": {"pace": 2.5, "acceleration": 2.0, "anticipation": 1.0, "positioning": 0.5},
        "FB": {"pace": 1.5, "acceleration": 1.5, "positioning": 0.5},
        "MID": {"positioning": 0.8, "anticipation": 0.8, "work_rate": 0.5},
        "GK": {"rushing_out": 1.0, "one_on_ones": 1.0},
    },
    MATCHUP_AERIAL: {
        "CB": {"jumping_reach": 2.5, "heading": 2.0, "strength": 1.5, "bravery": 0.5},
        "FB": {"jumping_reach": 0.8, "heading": 0.8},
        "MID": {"jumping_reach": 0.6, "strength": 0.8, "heading": 0.6},
        "GK": {"aerial_reach": 2.0, "command_of_area": 1.5, "punching": 0.5},
    },
    MATCHUP_FAVORITE: {
        "ATT": {"flair": 1.5, "dribbling": 1.5, "off_the_ball": 1.5, "vision": 1.0, "technique": 1.0, "composure": 0.8},
        "MID": {"vision": 1.5, "passing": 1.0, "technique": 0.8, "flair": 0.6},
        "FB": {"crossing": 1.0, "dribbling": 0.5},
    },
    MATCHUP_UNDERDOG: {
        "ATT": {"work_rate": 1.5, "teamwork": 0.8, "concentration": 0.6},
        "MID": {"work_rate": 1.5, "positioning": 1.5, "concentration": 1.2, "teamwork": 0.8},
        "FB": {"work_rate": 1.2, "positioning": 1.2, "concentration": 1.0},
        "CB": {"positioning": 1.5, "concentration": 1.5, "anticipation": 0.8},
        "GK": {"concentration": 1.0},
    },
}

# Matchday readiness (live fm.exe values; unknown values are never penalized).
SHARPNESS_OK = 75          # % - no penalty at or above
SHARPNESS_ALERT = 50       # % - warn below
SHARPNESS_MAX_PENALTY = 0.10
FATIGUE_OK = 300           # FM27 fatigue - no penalty at or below
FATIGUE_ALERT = 500        # warn above
FATIGUE_FULL = 1000        # maximum penalty reached here
FATIGUE_MAX_PENALTY = 0.15


def side_for_position(position: str) -> str:
    """Return the flank ("L"/"R"/"C") implied by an FM position code."""
    if position in LEFT_POSITIONS:
        return "L"
    if position in RIGHT_POSITIONS:
        return "R"
    return "C"


class RoleEvaluator:
    """Computes 0-100 role suitability scores for In Possession and Out of Possession."""

    def __init__(self, ip_roles_path: Path, oop_roles_path: Path) -> None:
        self.ip_roles: Dict[str, RoleDefinition] = self._load_roles(ip_roles_path, is_ip=True)
        self.oop_roles: Dict[str, RoleDefinition] = self._load_roles(oop_roles_path, is_ip=False)
        # Scoring context shared by the optimizer, bench and advisors (see configure()).
        self.scoring_mode: str = SCORING_FM_META
        self.matchup: str = MATCHUP_NEUTRAL
        self.factor_in_fitness: bool = True
        self._weights_cache: Dict[tuple, Dict[str, float]] = {}

    def configure(self, scoring_mode: str = SCORING_FM_META, matchup: str = MATCHUP_NEUTRAL,
                  factor_in_fitness: bool = True) -> None:
        """Set the Scoring Mode (FM Meta / Balanced), opponent Matchup and Factor in Fitness toggle."""
        if scoring_mode not in SCORING_MODES:
            raise ValueError(f"Unknown scoring mode {scoring_mode!r}; expected one of {SCORING_MODES}.")
        if matchup not in MATCHUPS:
            raise ValueError(f"Unknown matchup {matchup!r}; expected one of {MATCHUPS}.")
        self.scoring_mode, self.matchup, self.factor_in_fitness = scoring_mode, matchup, factor_in_fitness

    # ------------------------------------------------------------------ attribute weights
    def attribute_weights(self, role: RoleDefinition, slot_position: str) -> Dict[str, float]:
        """Role weights (primary 3.0 / secondary 1.5) plus the FM Meta and Matchup layers for this slot."""
        key = (role.name, role.slot_group, tuple(role.primary), tuple(role.secondary), slot_position,
               self.scoring_mode, self.matchup)
        cached = self._weights_cache.get(key)
        if cached is not None:
            return cached
        weights: Dict[str, float] = {}
        for attr in role.primary:
            weights[attr] = weights.get(attr, 0.0) + PRIMARY_WEIGHT
        for attr in role.secondary:
            weights[attr] = weights.get(attr, 0.0) + SECONDARY_WEIGHT
        is_gk_slot = slot_position == "GK" or role.slot_group == "GK"
        if self.scoring_mode == SCORING_FM_META:
            for attr, w in (META_WEIGHTS_GK if is_gk_slot else META_WEIGHTS_OUTFIELD).items():
                weights[attr] = weights.get(attr, 0.0) + w
        line = "GK" if is_gk_slot else POSITION_LINE.get(slot_position, "MID")
        for attr, w in MATCHUP_WEIGHTS.get(self.matchup, {}).get(line, {}).items():
            weights[attr] = weights.get(attr, 0.0) + w
        self._weights_cache[key] = weights
        return weights

    def attribute_contributions(self, player: Player, ip_role: str, oop_role: str, slot_position: str,
                                ip_share: float = 0.58) -> List[AttributeContribution]:
        """Blend of the IP and OOP weighted attributes, largest contribution first (for 'Why this XI?')."""
        blended: Dict[str, float] = {}
        for role, share in ((self.ip_roles[ip_role], ip_share), (self.oop_roles[oop_role], 1.0 - ip_share)):
            weights = self.attribute_weights(role, slot_position)
            total = sum(weights.values()) or 1.0
            for attr, w in weights.items():
                blended[attr] = blended.get(attr, 0.0) + share * w / total
        points = {a: w * player.visible.get(a, 10) for a, w in blended.items()}
        total_points = sum(points.values()) or 1.0
        out = [AttributeContribution(a, player.visible.get(a, 10), round(blended[a], 4),
                                     round(100.0 * p / total_points, 1)) for a, p in points.items()]
        out.sort(key=lambda c: -c.share)
        return out

    # ------------------------------------------------------------------ matchday readiness
    def fitness_status(self, player: Player) -> Tuple[float, Optional[Tuple[str, Dict[str, object]]]]:
        """(score multiplier, alert) from live Match Sharpness / Fatigue; (1.0, None) when unknown or disabled."""
        sharp, fatigue = player.match_sharpness, player.fatigue
        factor = 1.0
        if sharp is not None and sharp < SHARPNESS_OK:
            factor -= SHARPNESS_MAX_PENALTY * (SHARPNESS_OK - max(0, sharp)) / SHARPNESS_OK
        if fatigue is not None and fatigue > FATIGUE_OK:
            factor -= FATIGUE_MAX_PENALTY * min(1.0, (fatigue - FATIGUE_OK) / (FATIGUE_FULL - FATIGUE_OK))
        low_sharp = sharp is not None and sharp < SHARPNESS_ALERT
        tired = fatigue is not None and fatigue > FATIGUE_ALERT
        alert: Optional[Tuple[str, Dict[str, object]]] = None
        if low_sharp and tired:
            alert = ("fitness.alert.both", {"pct": sharp, "fatigue": fatigue})
        elif low_sharp:
            alert = ("fitness.alert.sharpness", {"pct": sharp})
        elif tired:
            alert = ("fitness.alert.fatigue", {"fatigue": fatigue})
        if not self.factor_in_fitness:
            return 1.0, alert
        return round(factor, 4), alert

    def fitness_factor(self, player: Player) -> float:
        return self.fitness_status(player)[0]

    @staticmethod
    def _load_roles(path: Path, is_ip: bool) -> Dict[str, RoleDefinition]:
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        roles: Dict[str, RoleDefinition] = {}
        for name, cfg in raw.items():
            roles[name] = RoleDefinition(
                name=name,
                slot_group=cfg["slot_group"],
                primary=cfg["primary"],
                secondary=cfg["secondary"],
                x=float(cfg["x"]),
                y=float(cfg["y"]),
                category=cfg.get("category", "") if is_ip else "",
                half_space=cfg.get("half_space", "center") if is_ip else "center",
                synergy_tags=cfg.get("synergy_tags", []) if is_ip else [],
            )
        return roles

    def _weighted_attribute_score(self, player: Player, role: RoleDefinition, slot_position: str) -> float:
        weights = self.attribute_weights(role, slot_position)
        total_w = sum(weights.values())
        if total_w == 0:
            return 50.0
        weighted_sum = sum(player.visible.get(attr, 10) * w for attr, w in weights.items())
        return (weighted_sum / (total_w * 20.0)) * 100.0

    @staticmethod
    def big_match_modifier(player: Player, big_match_mode: bool) -> float:
        """Return multiplier for Important Matches, Pressure, and Consistency."""
        if not big_match_mode:
            # Mild consistency factor even in normal matches
            return 0.96 + (player.hidden.consistency / 20.0) * 0.06
        imp = player.hidden.important_matches
        pres = player.hidden.pressure
        cons = player.hidden.consistency
        avg_mental = (imp * 0.45 + pres * 0.35 + cons * 0.20)
        if imp < 10 or pres < 10:
            return max(0.74, 0.85 + (avg_mental - 10.0) * 0.015)
        return min(1.10, 0.96 + (avg_mental - 10.0) * 0.014)

    @staticmethod
    def foot_modifier(player: Player, role_name: str, side: str) -> float:
        """Penalize wide roles played on the wrong foot (1.0 = ideal footedness)."""
        if side not in ("L", "R"):
            return 1.0
        same_side_foot = "Left" if side == "L" else "Right"
        if role_name in TOUCHLINE_ROLES:
            strength = player.foot_rating(same_side_foot)
            return 1.0 if strength >= 15 else (0.97 if strength >= 11 else 0.93)
        if role_name in INVERTED_ROLES:
            strength = player.foot_rating("Right" if side == "L" else "Left")
            return 1.0 if strength >= 15 else (0.975 if strength >= 11 else 0.95)
        return 1.0

    def score_ip_role(
        self,
        player: Player,
        role_name: str,
        slot_position: str,
        big_match_mode: bool = False,
        tactical_style: str = "Balanced Tactical Meta",
        side: str = "",
    ) -> float:
        """Score a player (0-100) for a specific In Possession role.

        ``side`` is the slot flank ("L"/"R"/"C"); when omitted it is derived from ``slot_position``.
        """
        role = self.ip_roles[role_name]
        attr_score = self._weighted_attribute_score(player, role, slot_position)
        ca_norm = min(100.0, (player.hidden.ca / 175.0) * 100.0)
        fam = player.familiarity_for(slot_position)
        raw = (attr_score * 0.75 + ca_norm * 0.25) * fam
        raw *= self.foot_modifier(player, role_name, side or side_for_position(slot_position))

        # Style-specific emphasis
        if tactical_style == "High-Scoring Attacking" and role.category in ("attacker", "striker", "midfield_creator"):
            raw *= 1.03
        elif tactical_style == "Proactive Possession" and ({"creator", "builder"} & set(role.synergy_tags)):
            raw *= 1.03
        elif tactical_style == "Fluid Counter-Attack" and (player.visible.pace >= 15 or player.visible.acceleration >= 15):
            raw *= 1.02

        raw *= self.big_match_modifier(player, big_match_mode)
        return round(max(1.0, min(99.5, raw)), 1)

    def score_oop_role(
        self,
        player: Player,
        role_name: str,
        slot_position: str,
        big_match_mode: bool = False,
        tactical_style: str = "Balanced Tactical Meta",
    ) -> float:
        """Score a player (0-100) for an Out of Possession defensive/pressing role."""
        role = self.oop_roles[role_name]
        attr_score = self._weighted_attribute_score(player, role, slot_position)
        ca_norm = min(100.0, (player.hidden.ca / 175.0) * 100.0)
        fam = player.familiarity_for(slot_position)
        raw = (attr_score * 0.80 + ca_norm * 0.20) * fam

        if tactical_style in ("High-Scoring Attacking", "Proactive Possession") and (
            role_name.startswith(AGGRESSIVE_OOP_PREFIXES) or role_name == "Sweeper Keeper"
        ):
            raw *= 1.03
        elif tactical_style == "Defensive Solidity" and role_name.startswith(CONSERVATIVE_OOP_PREFIXES):
            raw *= 1.04
        elif tactical_style == "Fluid Counter-Attack" and OUTLET_OOP_MARKER in role_name:
            raw *= 1.03

        raw *= self.big_match_modifier(player, big_match_mode)
        return round(max(1.0, min(99.5, raw)), 1)

    @staticmethod
    def mirror_x_for_side(x: float, side: str) -> float:
        """Mirror left-side role x-coordinate onto the right flank when needed."""
        if side == "R" and x < 50.0:
            return 100.0 - x
        if side == "L" and x > 50.0:
            return 100.0 - x
        return x

    def evaluate_transition_load(
        self,
        player: Player,
        ip_role_name: str,
        oop_role_name: str,
        side: str,
    ) -> Tuple[float, float, str | None]:
        """Compute spatial displacement between IP and OOP coordinates and fatigue penalty."""
        ip_role = self.ip_roles[ip_role_name]
        oop_role = self.oop_roles[oop_role_name]
        ip_x = self.mirror_x_for_side(ip_role.x, side)
        oop_x = self.mirror_x_for_side(oop_role.x, side)
        dist = math.hypot(ip_x - oop_x, ip_role.y - oop_role.y)

        engine_cap = (
            player.visible.stamina * 0.35
            + player.visible.work_rate * 0.30
            + player.visible.pace * 0.20
            + player.visible.natural_fitness * 0.15
        )
        # Max comfortable displacement scales with player engine capacity
        comfortable_dist = 18.0 + (engine_cap - 10.0) * 1.8
        if dist > comfortable_dist:
            excess = dist - comfortable_dist
            penalty = min(12.0, excess * 0.45)
            alert = (
                f"High Transition Load ({dist:.0f}m shift; Stamina {player.visible.stamina}/WR {player.visible.work_rate})"
            )
            return round(dist, 1), round(penalty, 1), alert
        return round(dist, 1), 0.0, None

    def best_overall_ip_role(self, player: Player) -> Tuple[str, float]:
        """Return the player's highest-rated In Possession role across their natural positions."""
        best_name, best_val = "Central Midfielder", 0.0
        for pos in player.positions:
            groups = POSITION_ROLE_GROUPS.get(pos, set())
            for r_name, r_def in self.ip_roles.items():
                if r_def.slot_group not in groups:
                    continue
                val = self.score_ip_role(player, r_name, pos)
                if val > best_val:
                    best_name, best_val = r_name, val
        return best_name, best_val

    def best_overall_oop_role(self, player: Player) -> Tuple[str, float]:
        """Return the player's highest-rated Out of Possession role across their natural positions."""
        best_name, best_val = "Central Midfielder", 0.0
        for pos in player.positions:
            groups = POSITION_ROLE_GROUPS.get(pos, set())
            for r_name, r_def in self.oop_roles.items():
                if r_def.slot_group not in groups:
                    continue
                val = self.score_oop_role(player, r_name, pos)
                if val > best_val:
                    best_name, best_val = r_name, val
        return best_name, best_val
