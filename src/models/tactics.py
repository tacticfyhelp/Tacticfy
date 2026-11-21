"""Tactical, role, instruction, and optimization result dataclasses."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.models.player import Player


TACTICAL_STYLES = [
    "High-Scoring Attacking",
    "Proactive Possession",
    "Balanced Tactical Meta",
    "Fluid Counter-Attack",
    "Defensive Solidity",
]


@dataclass
class RoleDefinition:
    """Role weight and coordinate definition for IP or OOP phase."""

    name: str
    slot_group: str
    primary: List[str]
    secondary: List[str]
    x: float
    y: float
    category: str = ""
    half_space: str = "center"
    synergy_tags: List[str] = field(default_factory=list)


@dataclass
class FormationSlot:
    """Single tactical slot inside a formation."""

    slot_id: str
    position: str
    side: str
    ip_roles: List[str]
    oop_roles: List[str]
    # Display-only textbook shape coordinates (x, y in 0-100); role math never uses these.
    ip_xy: Optional[Tuple[float, float]] = None
    oop_xy: Optional[Tuple[float, float]] = None


@dataclass
class FormationConfig:
    """Formation definition with 11 slots and style affinities."""

    name: str
    style_affinity: Dict[str, float]
    slots: List[FormationSlot]
    category: str = "standard"  # "standard" or "tactical_meta"


@dataclass
class AssignedSlot:
    """Solved player assignment for a specific tactical slot."""

    slot_id: str
    position: str
    side: str
    player: Player
    ip_role: str
    ip_score: float
    ip_coords: Tuple[float, float]
    oop_role: str
    oop_score: float
    oop_coords: Tuple[float, float]
    combined_score: float
    transition_distance: float
    transition_alert: Optional[str] = None
    individual_instructions: List[str] = field(default_factory=list)
    # Display-only symmetric formation coordinates (fall back to role coords when None).
    ip_display: Optional[Tuple[float, float]] = None
    oop_display: Optional[Tuple[float, float]] = None


@dataclass
class TeamInstructions:
    """Generated FM27 team instructions across all three phases."""

    tactical_style: str
    mentality: str
    in_possession: Dict[str, str]
    in_transition: Dict[str, str]
    out_of_possession: Dict[str, str]
    tactical_notes: List[str] = field(default_factory=list)


@dataclass
class LineupResult:
    """Complete optimization output for Best XI, Backup XI, and Instructions."""

    formation_name: str
    tactical_style: str
    big_match_mode: bool
    best_xi: List[AssignedSlot]
    backup_xi: List[AssignedSlot]
    team_synergy_score: float
    synergy_warnings: List[str]
    dropoff_by_slot: Dict[str, float]
    instructions: TeamInstructions


@dataclass
class PlayerClassification:
    """Squad advisor classification for an individual player."""

    player: Player
    category: str
    badge_color: str
    best_ip_role: str
    best_ip_score: float
    best_oop_role: str
    best_oop_score: float
    reasons: List[str]


@dataclass
class WeakestLinkReport:
    """Identifies the weakest starter / steepest depth drop-off and target profile."""

    weakest_slot_id: str
    weakest_player_name: str
    weakest_slot_score: float
    steepest_dropoff_slot: str
    steepest_dropoff_delta: float
    target_role: str
    target_position: str
    minimum_attributes: Dict[str, int]
    summary: str
