"""Player data models covering visible, hidden, contract, and positional attributes."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PlayerVisibleAttributes:
    """All 36 outfield and 11 goalkeeper visible FM attributes (1-20 scale)."""

    # Technical (14)
    corners: int = 10
    crossing: int = 10
    dribbling: int = 10
    finishing: int = 10
    first_touch: int = 10
    free_kick_taking: int = 10
    heading: int = 10
    long_shots: int = 10
    long_throws: int = 10
    marking: int = 10
    passing: int = 10
    penalty_taking: int = 10
    tackling: int = 10
    technique: int = 10

    # Mental (14)
    aggression: int = 10
    anticipation: int = 10
    bravery: int = 10
    composure: int = 10
    concentration: int = 10
    decisions: int = 10
    determination: int = 10
    flair: int = 10
    leadership: int = 10
    off_the_ball: int = 10
    positioning: int = 10
    teamwork: int = 10
    vision: int = 10
    work_rate: int = 10

    # Physical (8)
    acceleration: int = 10
    agility: int = 10
    balance: int = 10
    jumping_reach: int = 10
    natural_fitness: int = 10
    pace: int = 10
    stamina: int = 10
    strength: int = 10

    # Goalkeeping (11)
    aerial_reach: int = 5
    command_of_area: int = 5
    communication: int = 5
    eccentricity: int = 5
    handling: int = 5
    kicking: int = 5
    one_on_ones: int = 5
    punching: int = 5
    reflexes: int = 5
    rushing_out: int = 5
    throwing: int = 5

    def get(self, attr_name: str, default: int = 10) -> int:
        """Retrieve an attribute by name safely."""
        return int(getattr(self, attr_name, default))


@dataclass
class PlayerHiddenAttributes:
    """Hidden FM27 attributes extracted from memory or editor views."""

    ca: int = 110
    pa: int = 130
    consistency: int = 11
    important_matches: int = 11
    injury_proneness: int = 8
    professionalism: int = 12
    ambition: int = 12
    pressure: int = 11
    temperament: int = 12
    versatility: int = 11
    adaptability: int = 11
    loyalty: int = 11
    dirtiness: int = 8
    sportsmanship: int = 11
    controversy: int = 5


@dataclass
class Player:
    """Complete FM27 player representation."""

    player_id: int
    name: str
    age: int
    nationality: str = "Unknown"
    positions: List[str] = field(default_factory=lambda: ["MC"])
    position_familiarity: Dict[str, int] = field(default_factory=dict)
    preferred_foot: str = "Right"
    # Raw 1-20 foot strengths when known (live RAM reader); 0 = unknown -> derived from preferred_foot.
    left_foot: int = 0
    right_foot: int = 0
    wage_weekly: int = 5000
    market_value: int = 500000
    contract_expiry_year: int = 2028
    is_gk: bool = False
    visible: PlayerVisibleAttributes = field(default_factory=PlayerVisibleAttributes)
    hidden: PlayerHiddenAttributes = field(default_factory=PlayerHiddenAttributes)
    locked_starter: bool = False

    @property
    def pa_ca_delta(self) -> int:
        """Return remaining potential headroom."""
        return self.hidden.pa - self.hidden.ca

    def foot_rating(self, foot: str) -> int:
        """Return 1-20 strength of the given foot ("Left" or "Right")."""
        if self.left_foot and self.right_foot:
            return self.left_foot if foot == "Left" else self.right_foot
        if self.preferred_foot == "Either":
            return 17
        return 20 if self.preferred_foot == foot else 8

    # FM familiarity bands: Natural 18-20, Accomplished 15-17, Competent 12-14,
    # Unconvincing 9-11, Awkward 5-8, Ineffective 1-4. (rating, multiplier) anchor points.
    _FAMILIARITY_CURVE = ((1, 0.45), (5, 0.55), (9, 0.68), (12, 0.82), (15, 0.93), (18, 0.99), (20, 1.0))

    @classmethod
    def _familiarity_multiplier(cls, rating: int) -> float:
        rating = max(1, min(20, rating))
        curve = cls._FAMILIARITY_CURVE
        for (r0, m0), (r1, m1) in zip(curve, curve[1:]):
            if rating <= r1:
                return m0 + (m1 - m0) * (rating - r0) / (r1 - r0)
        return 1.0

    def familiarity_for(self, position: str) -> float:
        """Return positional familiarity multiplier in [0.25, 1.0]."""
        # Goalkeeper <-> outfield swaps are never realistic, whatever the raw familiarity byte says.
        if self.is_gk != (position == "GK"):
            return 0.25
        if position in self.position_familiarity:
            return self._familiarity_multiplier(self.position_familiarity[position])
        if position in self.positions:
            return 1.0
        # Partial credit for adjacent positions
        pos_group_map = {
            "GK": {"GK"},
            "DC": {"DC", "DM"},
            "DL": {"DL", "WBL", "DC", "ML"},
            "DR": {"DR", "WBR", "DC", "MR"},
            "WBL": {"WBL", "DL", "ML", "AML"},
            "WBR": {"WBR", "DR", "MR", "AMR"},
            "DM": {"DM", "MC", "DC"},
            "MC": {"MC", "DM", "AMC"},
            "AMC": {"AMC", "MC", "AML", "AMR", "ST"},
            "AML": {"AML", "ML", "WBL", "AMC", "ST"},
            "AMR": {"AMR", "MR", "WBR", "AMC", "ST"},
            "ST": {"ST", "AMC", "AML", "AMR"},
        }
        related = pos_group_map.get(position, set())
        if any(p in related for p in self.positions):
            return 0.82
        return 0.60
