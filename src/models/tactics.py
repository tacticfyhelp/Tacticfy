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

SCORING_FM_META = "FM Meta"
SCORING_BALANCED = "Balanced"
SCORING_MODES = [SCORING_FM_META, SCORING_BALANCED]  # FM Meta is the default

MATCHUP_NEUTRAL = "Neutral"
MATCHUP_FAVORITE = "Favorite vs Low Block"
MATCHUP_UNDERDOG = "Underdog vs Stronger"
MATCHUP_FAST_COUNTER = "vs Fast Counter"
MATCHUP_AERIAL = "vs Aerial / Direct"
MATCHUPS = [MATCHUP_NEUTRAL, MATCHUP_FAVORITE, MATCHUP_UNDERDOG, MATCHUP_FAST_COUNTER, MATCHUP_AERIAL]


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
    # Matchday readiness: (translation key, args) when the player is unsharp / tired, and the score multiplier.
    fitness_alert: Optional[Tuple[str, Dict[str, object]]] = None
    fitness_factor: float = 1.0


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
    scoring_mode: str = "FM Meta"
    matchup: str = "Neutral"
    factor_in_fitness: bool = True
    # Every evaluated formation with its Team Synergy score, best first ("why this formation?").
    formation_ranking: List[Tuple[str, float]] = field(default_factory=list)
    excluded_count: int = 0


@dataclass
class AttributeContribution:
    """One attribute's share of a player's weighted role score."""

    attr: str
    value: int
    weight: float
    share: float  # % of the weighted attribute score


@dataclass
class ScoreDriver:
    """Why the selected player beat the runner-up: score points gained from one attribute group."""

    attrs: Tuple[str, ...]   # attribute keys, or a pseudo key such as "ca" / "familiarity" / "fitness"
    delta: float             # >0 favours the selected player, <0 favours the runner-up


@dataclass
class SlotExplanation:
    """'Why this XI?' breakdown for one slot."""

    slot_id: str
    player: Player
    score: float
    top_attributes: List[AttributeContribution]
    runner_up: Optional[Player] = None
    runner_up_score: float = 0.0
    drivers: List[ScoreDriver] = field(default_factory=list)

    @property
    def gap(self) -> float:
        return round(self.score - self.runner_up_score, 1)


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
