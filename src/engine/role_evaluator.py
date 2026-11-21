"""Evaluates FM27 players for both In Possession and Out of Possession roles."""

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

from src.models.player import Player
from src.models.tactics import RoleDefinition


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

    @staticmethod
    def _weighted_attribute_score(player: Player, primary: List[str], secondary: List[str]) -> float:
        total_w = 0.0
        weighted_sum = 0.0
        for attr in primary:
            w = 3.0
            weighted_sum += player.visible.get(attr, 10) * w
            total_w += w
        for attr in secondary:
            w = 1.5
            weighted_sum += player.visible.get(attr, 10) * w
            total_w += w
        if total_w == 0:
            return 50.0
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
        attr_score = self._weighted_attribute_score(player, role.primary, role.secondary)
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
        attr_score = self._weighted_attribute_score(player, role.primary, role.secondary)
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
