"""Generates FM27 Team Instructions and Player Instructions in the game's own tile vocabulary.

Every team instruction is emitted as ``{tile title: setting}`` and every player instruction as
``"Tile: Setting"``. Titles and settings come from config/fm27_tactics_reference.json, which
tools/extract_fm27_tactics.py extracts from the installed game; anything outside that catalogue
raises immediately, so the generator can never drift back to legacy (FM24) wording.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

from src.app_paths import resource_path
from src.models.player import Player
from src.models.tactics import (
    MATCHUP_AERIAL, MATCHUP_FAST_COUNTER, MATCHUP_FAVORITE, MATCHUP_NEUTRAL, MATCHUP_UNDERDOG,
    AssignedSlot, TeamInstructions,
)

REFERENCE_PATH = resource_path("config", "fm27_tactics_reference.json")
NO_PI_TWEAKS = "No individual tweaks (role defaults)"

ATTACK_POSITIONS = {"AML", "AMR", "AMC", "ST", "ML", "MR"}
WIDE_DEFENDERS = {"DL", "DR", "WBL", "WBR"}
WIDE_POSITIONS = WIDE_DEFENDERS | {"AML", "AMR", "ML", "MR"}
LEFT_POSITIONS = {"DL", "WBL", "ML", "AML"}
RIGHT_POSITIONS = {"DR", "WBR", "MR", "AMR"}

# FM27 In Possession role families
CREATOR_ROLES = {"Deep-Lying Playmaker", "Midfield Playmaker", "Advanced Playmaker", "Box-To-Box Playmaker",
                 "Playmaking Winger", "Playmaking Wing-Back", "Free Role", "False Nine", "Ball-Playing Centre-Back"}
PLAYMAKER_ROLES = {"Deep-Lying Playmaker", "Midfield Playmaker", "Advanced Playmaker", "Box-To-Box Playmaker"}
HOLDING_ROLES = {"Defensive Midfielder", "Half Back", "Centre-Back", "No-Nonsense Centre-Back",
                 "Ball-Playing Centre-Back", "Wide Centre-Back", "Inside Full-Back", "Inside Wing-Back"}
TOUCHLINE_CROSSERS_BYLINE = {"Winger", "Wide Forward", "Advanced Wing-Back", "Overlapping Centre-Back"}
TOUCHLINE_CROSSERS_DEEP = {"Wide Midfielder", "Full-Back", "Wing-Back", "Wide Central Midfielder"}
INVERTING_ROLES = {"Inside Forward", "Inside Winger"}
UNDERLAPPING_ROLES = {"Inside Full-Back", "Inside Wing-Back", "Playmaking Wing-Back"}
LATE_RUNNER_ROLES = {"Box-To-Box Midfielder", "Channel Midfielder", "Central Midfielder", "Box-To-Box Playmaker"}
TARGET_ROLES = {"Target Forward", "Deep-Lying Forward"}

# Ordered FM27 settings so the squad profile can nudge a style baseline by one step.
TRIGGER_PRESS_SCALE = ["Much Less Often", "Less Often", "Standard", "More Often", "Much More Often"]
LINE_SCALE = ["Much Lower", "Lower", "Standard", "Higher", "Much Higher"]

STRONG = 13.0  # "clear strength" threshold for XI averages (1-20 scale)
WEAK = 10.5    # "clear weakness" threshold


# ----------------------------------------------------------------------------------- vocabulary
@lru_cache(maxsize=1)
def fm27_catalogue() -> Tuple[Dict[str, List[str]], Dict[str, str], Dict[str, List[str]], Tuple[str, ...]]:
    """Return (team tiles -> options, team tile -> phase label, player tiles -> options, mentalities)."""
    ref = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    team: Dict[str, List[str]] = {}
    phase: Dict[str, str] = {}
    for ti in ref["team_instructions"]:
        team[ti["title"]] = ti["options"]
        phase.setdefault(ti["title"], f"{ti['section']} - {ti['phase']}")
    player = {pi["title"]: pi["options"] for pi in ref["player_instructions"]}
    return team, phase, player, tuple(ref["mentalities"])


def _check_team(tile: str, setting: str) -> None:
    team, _, _, _ = fm27_catalogue()
    if tile not in team or setting not in team[tile]:
        raise ValueError(f"Not an FM27 team instruction: {tile!r} = {setting!r}")


def _check_player(tile: str, setting: str) -> None:
    _, _, player, _ = fm27_catalogue()
    if tile not in player or setting not in player[tile]:
        raise ValueError(f"Not an FM27 player instruction: {tile!r} = {setting!r}")


class _TI(dict):
    """Ordered {tile: setting} that validates every write against the FM27 catalogue."""

    def __setitem__(self, tile: str, setting: str) -> None:
        _check_team(tile, setting)
        super().__setitem__(tile, setting)


def _avg(values: Iterable[float], default: float = 10.0) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else default


def _shift(scale: List[str], value: str, steps: int) -> str:
    idx = scale.index(value) if value in scale else len(scale) // 2
    return scale[max(0, min(len(scale) - 1, idx + steps))]


@dataclass
class SquadProfile:
    """Averages of the selected XI that drive instruction choices."""

    passing: float
    build_up_passing: float    # GK + centre-backs + defensive midfielders
    attack_pace: float
    attack_dribbling: float
    long_shots: float
    cb_pace: float
    cb_reading: float          # anticipation + concentration + positioning
    engine: float              # work rate + stamina across outfielders
    aggression: float
    dirtiness: float
    aerial_target: float       # best striker (jumping reach + heading) / 2
    wide_crossing: float
    left_threat: float
    right_threat: float
    central_creativity: float
    gk: Optional[Player]


class InstructionsGenerator:
    """Builds adaptive FM27 team and individual instructions from the solved Best XI."""

    @staticmethod
    def build_profile(best_xi: List[AssignedSlot]) -> SquadProfile:
        outfield = [a.player for a in best_xi if a.position != "GK"]
        attackers = [a.player for a in best_xi if a.position in ATTACK_POSITIONS]
        cbs = [a.player for a in best_xi if a.position == "DC"]
        builders = [a.player for a in best_xi if a.position in ("GK", "DC", "DM")]
        strikers = [a.player for a in best_xi if a.position == "ST"]
        wide = [a.player for a in best_xi if a.position in WIDE_POSITIONS]
        shooters = [a.player for a in best_xi if a.position in ATTACK_POSITIONS | {"MC", "DM"}]
        central = [a.player for a in best_xi if a.position in ("MC", "AMC", "DM")]
        gk = next((a.player for a in best_xi if a.position == "GK"), None)

        def flank(positions: set) -> float:
            ps = [a.player for a in best_xi if a.position in positions]
            return _avg((p.visible.crossing + p.visible.dribbling + p.visible.pace) / 3 for p in ps)

        return SquadProfile(
            passing=_avg(p.visible.passing for p in outfield),
            build_up_passing=_avg((p.visible.passing + p.visible.composure + p.visible.first_touch) / 3 for p in builders),
            attack_pace=_avg((p.visible.pace + p.visible.acceleration) / 2 for p in attackers),
            attack_dribbling=_avg(p.visible.dribbling for p in attackers),
            long_shots=_avg(p.visible.long_shots for p in shooters),
            cb_pace=_avg(p.visible.pace for p in cbs),
            cb_reading=_avg(
                (p.visible.anticipation + p.visible.concentration + p.visible.positioning) / 3 for p in cbs
            ),
            engine=_avg((p.visible.work_rate + p.visible.stamina) / 2 for p in outfield),
            aggression=_avg(p.visible.aggression for p in outfield),
            dirtiness=_avg(p.hidden.dirtiness for p in outfield),
            aerial_target=max(((p.visible.jumping_reach + p.visible.heading) / 2 for p in strikers), default=10.0),
            wide_crossing=_avg(p.visible.crossing for p in wide),
            left_threat=flank(LEFT_POSITIONS),
            right_threat=flank(RIGHT_POSITIONS),
            central_creativity=_avg((p.visible.passing + p.visible.vision + p.visible.technique) / 3 for p in central),
            gk=gk,
        )

    # ------------------------------------------------------------------------------- baselines
    @staticmethod
    def _baseline(style: str) -> Tuple[str, Dict[str, str], Dict[str, str], Dict[str, str]]:
        """Style baseline in FM27 settings: (mentality, in possession, in transition, out of possession)."""
        if style == "High-Scoring Attacking":
            return "Attacking", {
                "Directness": "Shorter", "Tempo": "Much Higher", "Team Width": "Wider",
                "Creative Freedom": "More Expressive", "Time Wasting": "Less Often",
                "Play for Set Pieces": "Keep Ball in Play",
                "Build-Up Strategy": "Play Through Press", "Goal Kicks": "Short",
                "GK Distribution (Speed)": "Distribute Quickly",
                "Supporting Runs": "Balanced", "Dribbling": "Standard", "Progress Through": "Balanced",
                "Pass Reception": "Pass Into Space",
                "Patience": "Standard", "Shots from Distance": "Balanced",
            }, {"Attacking Transition": "Counter-Attack", "Defensive Transition": "Counter-Press"}, {
                "Line of Engagement": "High Press", "Defensive Line": "Higher",
                "Defensive Line Behaviour": "Step Up More", "Trigger Press": "Much More Often",
                "Tackling": "Standard", "Pressing Trap": "Trap Outside",
                "Prevent Short GK Distribution": "Yes", "Cross Engagement": "Balanced",
            }
        if style == "Proactive Possession":
            return "Positive", {
                "Directness": "Much Shorter", "Tempo": "Lower", "Team Width": "Narrower",
                "Creative Freedom": "More Expressive", "Time Wasting": "Standard",
                "Play for Set Pieces": "Keep Ball in Play",
                "Build-Up Strategy": "Play Through Press", "Goal Kicks": "Short",
                "GK Distribution (Speed)": "Balanced",
                "Supporting Runs": "Balanced", "Dribbling": "Standard", "Progress Through": "Balanced",
                "Pass Reception": "Pass Into Feet",
                "Patience": "Work Ball Into Box", "Shots from Distance": "Discourage",
            }, {"Attacking Transition": "Hold Shape", "Defensive Transition": "Counter-Press"}, {
                "Line of Engagement": "High Press", "Defensive Line": "Higher",
                "Defensive Line Behaviour": "Step Up More", "Trigger Press": "More Often",
                "Tackling": "Standard", "Pressing Trap": "Trap Inside",
                "Prevent Short GK Distribution": "Yes", "Cross Engagement": "Balanced",
            }
        if style == "Fluid Counter-Attack":
            return "Balanced", {
                "Directness": "More Direct", "Tempo": "Higher", "Team Width": "Standard",
                "Creative Freedom": "Balanced", "Time Wasting": "Standard",
                "Play for Set Pieces": "Keep Ball in Play",
                "Build-Up Strategy": "Bypass Press", "Goal Kicks": "Mixed",
                "GK Distribution (Speed)": "Distribute Quickly",
                "Supporting Runs": "Balanced", "Dribbling": "Standard", "Progress Through": "Balanced",
                "Pass Reception": "Pass Into Space",
                "Patience": "Standard", "Shots from Distance": "Balanced",
            }, {"Attacking Transition": "Counter-Attack", "Defensive Transition": "Regroup"}, {
                "Line of Engagement": "Mid Block", "Defensive Line": "Standard",
                "Defensive Line Behaviour": "Drop Off More", "Trigger Press": "Standard",
                "Tackling": "Standard", "Pressing Trap": "Trap Outside",
                "Prevent Short GK Distribution": "No", "Cross Engagement": "Balanced",
            }
        if style == "Defensive Solidity":
            return "Cautious", {
                "Directness": "Standard", "Tempo": "Lower", "Team Width": "Narrower",
                "Creative Freedom": "More Disciplined", "Time Wasting": "More Often",
                "Play for Set Pieces": "Play for Set Pieces",
                "Build-Up Strategy": "Bypass Press", "Goal Kicks": "Mixed",
                "GK Distribution (Speed)": "Slow Pace Down",
                "Supporting Runs": "Balanced", "Dribbling": "Discourage", "Progress Through": "Balanced",
                "Pass Reception": "Standard",
                "Patience": "Standard", "Shots from Distance": "Balanced",
            }, {"Attacking Transition": "Hold Shape", "Defensive Transition": "Regroup"}, {
                "Line of Engagement": "Low Block", "Defensive Line": "Lower",
                "Defensive Line Behaviour": "Drop Off More", "Trigger Press": "Less Often",
                "Tackling": "Ease Off Tackles", "Pressing Trap": "Trap Inside",
                "Prevent Short GK Distribution": "No", "Cross Engagement": "Stop Crosses",
            }
        # Balanced Tactical Meta
        return "Positive", {
            "Directness": "Standard", "Tempo": "Higher", "Team Width": "Standard",
            "Creative Freedom": "Balanced", "Time Wasting": "Standard",
            "Play for Set Pieces": "Keep Ball in Play",
            "Build-Up Strategy": "Balanced", "Goal Kicks": "Mixed", "GK Distribution (Speed)": "Balanced",
            "Supporting Runs": "Balanced", "Dribbling": "Standard", "Progress Through": "Balanced",
            "Pass Reception": "Standard",
            "Patience": "Standard", "Shots from Distance": "Balanced",
        }, {"Attacking Transition": "Counter-Attack", "Defensive Transition": "Counter-Press"}, {
            "Line of Engagement": "Mid Block", "Defensive Line": "Standard",
            "Defensive Line Behaviour": "Balanced", "Trigger Press": "More Often",
            "Tackling": "Standard", "Pressing Trap": "Trap Outside",
            "Prevent Short GK Distribution": "No", "Cross Engagement": "Balanced",
        }

    # ------------------------------------------------------------------------------- generate
    def generate(
        self,
        best_xi: List[AssignedSlot],
        tactical_style: str,
        synergy_warnings: List[str],
        matchup: str = MATCHUP_NEUTRAL,
    ) -> TeamInstructions:
        """Generate FM27 team and per-player instructions tailored to style and squad traits."""
        prof = self.build_profile(best_xi)
        notes: List[str] = list(synergy_warnings)
        mentality, ip_base, trans_base, oop_base = self._baseline(tactical_style)
        if mentality not in fm27_catalogue()[3]:
            raise ValueError(f"Not an FM27 mentality: {mentality!r}")
        ip, trans, oop = _TI(ip_base), _TI(trans_base), _TI(oop_base)
        for d in (ip, trans, oop):  # validate the baselines too
            for k, v in list(d.items()):
                d[k] = v
        ip_roles = {a.ip_role for a in best_xi}

        # ---- In Possession: build-up --------------------------------------------------------
        if ip["Build-Up Strategy"] == "Play Through Press" and prof.build_up_passing <= WEAK:
            ip["Build-Up Strategy"] = "Balanced"
            notes.append(f"Build-Up Risk: GK/CB/DM passing averages {prof.build_up_passing:.1f}; "
                         "Build-Up Strategy relaxed to Balanced.")
        if prof.passing <= WEAK and ip["Directness"] in ("Much Shorter", "Shorter"):
            ip["Directness"] = "Standard"
            notes.append(f"Passing Risk: XI averages {prof.passing:.1f} Passing; Directness relaxed to Standard.")
        elif prof.passing >= STRONG and ip["Directness"] == "Standard" and tactical_style != "Fluid Counter-Attack":
            ip["Directness"] = "Shorter"
        if prof.aerial_target >= 14.0 and ip["Goal Kicks"] == "Mixed" and tactical_style != "Proactive Possession":
            ip["Goal Kicks"] = "Long"
        ip["GK Distribution"] = self._gk_distribution(prof, ip, ip_roles)

        # ---- In Possession: progression -------------------------------------------------------
        underlap_left = any(a.ip_role in UNDERLAPPING_ROLES and a.position in LEFT_POSITIONS for a in best_xi)
        underlap_right = any(a.ip_role in UNDERLAPPING_ROLES and a.position in RIGHT_POSITIONS for a in best_xi)
        if underlap_left and underlap_right:
            ip["Supporting Runs"] = "Underlap Both Flanks"
        elif underlap_left:
            ip["Supporting Runs"] = "Underlap Left Flank"
        elif underlap_right:
            ip["Supporting Runs"] = "Underlap Right Flank"
        if prof.attack_dribbling >= STRONG and tactical_style != "Defensive Solidity":
            ip["Dribbling"] = "Encourage"
            notes.append(f"Dribbling Edge: attackers average {prof.attack_dribbling:.1f} Dribbling; Dribbling encouraged.")
        ip["Progress Through"] = self._progress_through(prof)

        # ---- In Possession: final third -------------------------------------------------------
        if prof.long_shots >= STRONG:
            ip["Shots from Distance"] = "Encourage"
        elif prof.long_shots <= 9.5:
            ip["Shots from Distance"] = "Discourage"
        aerial = prof.aerial_target >= 14.0
        if aerial and prof.wide_crossing >= 12.0:
            ip["Crossing Style"] = "Whipped Crosses"
        elif aerial:
            ip["Crossing Style"] = "Floated Crosses"
        elif prof.wide_crossing <= WEAK or tactical_style == "Proactive Possession":
            ip["Crossing Style"] = "Low Crosses"
        else:
            ip["Crossing Style"] = "Balanced"
        if aerial:
            notes.append(f"Aerial Target: best striker rates {prof.aerial_target:.1f} (Jumping/Heading); crosses are a weapon.")
        else:
            notes.append(f"Ground Threat: best striker aerial rating is only {prof.aerial_target:.1f}; keep crosses low.")

        # ---- In Transition ---------------------------------------------------------------------
        if trans["Attacking Transition"] == "Counter-Attack" and prof.attack_pace <= WEAK:
            trans["Attacking Transition"] = "Standard"
            notes.append(f"Slow Front Line: attackers average {prof.attack_pace:.1f} Pace/Acceleration; "
                         "Attacking Transition set to Standard.")
        elif trans["Attacking Transition"] == "Hold Shape" and prof.attack_pace >= 14.0:
            trans["Attacking Transition"] = "Counter-Attack"
            notes.append(f"Pace Outlet: attackers average {prof.attack_pace:.1f} Pace/Acceleration; Counter-Attack enabled.")
        if trans["Defensive Transition"] == "Counter-Press" and prof.engine <= WEAK:
            trans["Defensive Transition"] = "Regroup"
            notes.append(f"Low Engine: XI averages {prof.engine:.1f} Work Rate/Stamina; Regroup instead of Counter-Press.")

        # ---- Out of Possession -----------------------------------------------------------------
        if prof.engine >= 14.0:
            oop["Trigger Press"] = _shift(TRIGGER_PRESS_SCALE, oop["Trigger Press"], +1)
        elif prof.engine <= 11.0:
            oop["Trigger Press"] = _shift(TRIGGER_PRESS_SCALE, oop["Trigger Press"], -1)
            notes.append(f"Pressing Load: XI averages {prof.engine:.1f} Work Rate/Stamina; Trigger Press reduced.")

        if prof.cb_pace < 11.5 and oop["Defensive Line"] in ("Higher", "Much Higher"):
            oop["Defensive Line"] = "Standard"
            if oop["Line of Engagement"] == "High Press":
                oop["Line of Engagement"] = "Mid Block"
            if oop["Defensive Line Behaviour"] == "Step Up More":
                oop["Defensive Line Behaviour"] = "Balanced"
            notes.append(f"High-Line Risk: centre-backs average {prof.cb_pace:.1f} Pace; Defensive Line set to Standard.")
        elif prof.cb_pace >= 14.0 and oop["Defensive Line"] in ("Standard", "Lower"):
            oop["Defensive Line"] = _shift(LINE_SCALE, oop["Defensive Line"], +1)
        if (prof.cb_reading >= STRONG and prof.cb_pace >= 12.0
                and oop["Defensive Line"] in ("Higher", "Much Higher")):
            oop["Defensive Line Behaviour"] = "Step Up More"
        notes.extend(self._apply_matchup(matchup, prof, ip, trans, oop))
        oop["Prevent Short GK Distribution"] = "Yes" if oop["Line of Engagement"] == "High Press" else "No"

        if prof.dirtiness >= 12.0:
            oop["Tackling"] = "Ease Off Tackles"
            notes.append(f"Card Risk: XI averages {prof.dirtiness:.1f} Dirtiness; Tackling set to Ease Off Tackles.")
        elif prof.aggression >= STRONG and prof.dirtiness <= 10.0 and oop["Tackling"] == "Standard":
            oop["Tackling"] = "Tackle Harder"

        notes.extend(self._set_piece_notes(best_xi))

        for slot in best_xi:
            slot.individual_instructions = self._build_player_instructions(slot, tactical_style, prof)

        return TeamInstructions(
            tactical_style=tactical_style,
            mentality=mentality,
            in_possession=dict(self._ordered(ip)),
            in_transition=dict(trans),
            out_of_possession=dict(self._ordered(oop)),
            tactical_notes=notes,
        )

    @staticmethod
    def _apply_matchup(matchup: str, prof: SquadProfile, ip: Dict[str, str], trans: Dict[str, str],
                       oop: Dict[str, str]) -> List[str]:
        """Adapt the FM27 Team Instructions to the opponent matchup; returns the tactical notes."""
        if matchup == MATCHUP_FAST_COUNTER:
            # Deny space in behind: drop the line a step, retreat on loss of the ball.
            oop["Defensive Line"] = _shift(LINE_SCALE, oop["Defensive Line"], -1)
            oop["Defensive Line Behaviour"] = "Drop Off More"
            if oop["Line of Engagement"] == "High Press":
                oop["Line of Engagement"] = "Mid Block"
            trans["Defensive Transition"] = "Regroup"
            return [f"Matchup vs Fast Counter: Defensive Line {oop['Defensive Line']}, Drop Off More and Regroup "
                    f"(centre-backs average {prof.cb_pace:.1f} Pace)."]
        if matchup == MATCHUP_AERIAL:
            oop["Cross Engagement"] = "Stop Crosses"
            oop["Defensive Line Behaviour"] = "Drop Off More"
            if oop["Defensive Line"] in ("Higher", "Much Higher"):
                oop["Defensive Line"] = "Standard"
            return ["Matchup vs Aerial / Direct: Stop Crosses and Drop Off More to win the first header in front "
                    "of goal."]
        if matchup == MATCHUP_FAVORITE:
            ip["Patience"] = "Work Ball Into Box"
            ip["Team Width"] = _shift(["Much Narrower", "Narrower", "Standard", "Wider", "Much Wider"],
                                      ip["Team Width"], +1)
            ip["Creative Freedom"] = "More Expressive"
            trans["Defensive Transition"] = "Counter-Press"
            if oop["Line of Engagement"] == "Low Block":
                oop["Line of Engagement"] = "Mid Block"
            return [f"Matchup Favorite vs Low Block: Work Ball Into Box, Team Width {ip['Team Width']}, More "
                    "Expressive and Counter-Press to pin the opponent in."]
        if matchup == MATCHUP_UNDERDOG:
            engagement = {"High Press": "Mid Block", "Mid Block": "Low Block"}
            oop["Line of Engagement"] = engagement.get(oop["Line of Engagement"], oop["Line of Engagement"])
            oop["Defensive Line"] = _shift(LINE_SCALE, oop["Defensive Line"], -1)
            oop["Trigger Press"] = _shift(TRIGGER_PRESS_SCALE, oop["Trigger Press"], -1)
            trans["Defensive Transition"] = "Regroup"
            trans["Attacking Transition"] = "Counter-Attack" if prof.attack_pace >= 12.0 else "Standard"
            ip["Directness"] = _shift(["Much Shorter", "Shorter", "Standard", "More Direct", "Much More Direct"],
                                      ip["Directness"], +1)
            return [f"Matchup Underdog vs Stronger: {oop['Line of Engagement']}, Regroup and "
                    f"{trans['Attacking Transition']} on the break; stay compact and disciplined."]
        return []

    PHASE_ORDER = [
        "In Possession - Overview", "In Possession - Build-Up", "In Possession - Progression",
        "In Possession - Final Third", "Out of Possession - Overview", "Out of Possession - High Press",
        "Out of Possession - Mid Block", "Out of Possession - Low Block",
    ]

    @classmethod
    def _ordered(cls, tiles: Dict[str, str]) -> List[Tuple[str, str]]:
        """Order tiles the way the FM27 tactics screen walks the phases, then by catalogue order."""
        team, phase, _, _ = fm27_catalogue()
        order = {title: i for i, title in enumerate(team)}

        def key(kv: Tuple[str, str]) -> Tuple[int, int]:
            ph = phase.get(kv[0], "")
            return (cls.PHASE_ORDER.index(ph) if ph in cls.PHASE_ORDER else 99, order.get(kv[0], 999))

        return sorted(tiles.items(), key=key)

    @staticmethod
    def phase_of(tile: str) -> str:
        """FM27 tactics-screen section for a team instruction tile, e.g. 'In Possession - Build-Up'."""
        return fm27_catalogue()[1].get(tile, "")

    @staticmethod
    def _gk_distribution(prof: SquadProfile, ip: Dict[str, str], ip_roles: set) -> str:
        gk = prof.gk
        if gk is None:
            return "Balanced"
        if ip.get("Goal Kicks") == "Long" or (gk.visible.kicking >= 13 and prof.aerial_target >= 14.0
                                              and ("Target Forward" in ip_roles or "Deep-Lying Forward" in ip_roles)):
            return "Distribute to Target Forward"
        if ip.get("Build-Up Strategy") == "Play Through Press" and gk.visible.passing >= 11:
            return "Distribute to Centre-Backs"
        if ip_roles & PLAYMAKER_ROLES and gk.visible.passing >= 12:
            return "Distribute to Playmaker"
        if gk.visible.kicking >= 13 and prof.attack_pace >= 13.5:
            return "Distribute Over Opposition Defence"
        if prof.wide_crossing >= 12.0 and gk.visible.throwing >= 12:
            return "Distribute To Full-Backs"
        return "Balanced"

    @staticmethod
    def _progress_through(prof: SquadProfile) -> str:
        flanks = (prof.left_threat + prof.right_threat) / 2
        if prof.left_threat - prof.right_threat >= 1.5:
            return "Progress Through Left Flank"
        if prof.right_threat - prof.left_threat >= 1.5:
            return "Progress Through Right Flank"
        if prof.central_creativity - flanks >= 1.5:
            return "Progress Through the Middle"
        if flanks - prof.central_creativity >= 1.5:
            return "Progress Through Both Flanks"
        return "Balanced"

    @staticmethod
    def _set_piece_notes(best_xi: List[AssignedSlot]) -> List[str]:
        players = [a.player for a in best_xi]
        if not players:
            return []
        picks = []
        for label, attr in (("Corners", "corners"), ("Free Kicks", "free_kick_taking"), ("Penalties", "penalty_taking")):
            best = max(players, key=lambda p, a=attr: p.visible.get(a))
            picks.append(f"{label}: {best.name.split()[-1]} ({best.visible.get(attr)})")
        return ["Set-Piece Takers: " + ", ".join(picks) + "."]

    # ------------------------------------------------------------------------------- player
    @staticmethod
    def _build_player_instructions(slot: AssignedSlot, tactical_style: str, prof: SquadProfile) -> List[str]:
        """FM27 player instruction tiles as "Tile: Setting" (one setting per tile)."""
        p, v = slot.player, slot.player.visible
        role, pos = slot.ip_role, slot.position
        tiles: Dict[str, str] = {}

        def put(tile: str, setting: str) -> None:
            if tile not in tiles:
                _check_player(tile, setting)
                tiles[tile] = setting

        if pos == "GK":
            if role == "Ball-Playing Goalkeeper" and v.passing >= 12:
                put("Passing Strategy", "Shorter")
            elif v.kicking >= 14 and role != "Ball-Playing Goalkeeper":
                put("Passing Strategy", "More Direct")
            if v.passing < 11:
                put("Passing Risk", "Take Fewer Risks")
            return [f"{k}: {s}" for k, s in tiles.items()] or [NO_PI_TWEAKS]

        # Passing
        if role in CREATOR_ROLES and v.vision >= 14 and v.passing >= 14:
            put("Passing Risk", "Take More Risks")
        elif role in HOLDING_ROLES and v.passing < 12:
            put("Passing Risk", "Take Fewer Risks")

        # Width and dribbling
        if role in TOUCHLINE_CROSSERS_BYLINE | TOUCHLINE_CROSSERS_DEEP and pos in WIDE_POSITIONS:
            put("Attacking Width", "Stay Wider")
        if role in INVERTING_ROLES and v.dribbling >= 13:
            put("Dribbling Direction", "Cut Inside With Ball")
        if pos in ATTACK_POSITIONS | WIDE_DEFENDERS:
            if v.dribbling >= 14:
                put("Dribbling Frequency", "Dribble More")
            elif v.dribbling <= 8:
                put("Dribbling Frequency", "Dribble Less")

        # Crossing
        if v.crossing >= 13 and pos in WIDE_POSITIONS and role not in INVERTING_ROLES:
            if role in TOUCHLINE_CROSSERS_BYLINE:
                put("Cross From", "Byline")
            elif role in TOUCHLINE_CROSSERS_DEEP:
                put("Cross From", "Cross From Deep")
            if prof.aerial_target >= 14.0:
                put("Crossing Strategy", "Cross to Target Forward")
            else:
                put("Crossing Strategy", "Cross to Near Post" if v.crossing >= 15 else "Cross to Centre")

        # Shooting
        if pos not in ("DC", "GK"):
            if v.long_shots >= 14 and pos in ATTACK_POSITIONS | {"MC", "DM"}:
                put("Shooting", "Shoot More Often")
            elif v.long_shots <= 9:
                put("Shooting", "Shoot Less Often")

        # Movement
        if pos == "ST" and role not in TARGET_ROLES | {"False Nine"} and (v.pace + v.acceleration) / 2 >= 14:
            put("Attack Box - Depth", "Attack Defensive Line")
        elif role in LATE_RUNNER_ROLES and v.off_the_ball >= 13:
            put("Attack Box - Depth", "Arrive Late in Box")
        if role in TARGET_ROLES and v.strength >= 14:
            put("Hold Up Ball", "Yes")
        if role in CREATOR_ROLES and v.flair >= 15 and role != "Free Role":
            put("Freedom of Movement", "Roam From Position")
        if slot.transition_alert and pos not in ATTACK_POSITIONS:
            put("Forward Runs", "Make Fewer Runs")
        elif role in HOLDING_ROLES and tactical_style == "Defensive Solidity":
            put("Forward Runs", "Make Fewer Runs")

        # Out of possession
        if v.tackling >= 14 and p.hidden.dirtiness <= 9 and tactical_style in ("High-Scoring Attacking", "Proactive Possession"):
            put("Tackling", "Tackle Harder")
        elif p.hidden.dirtiness >= 14 and pos in ("DC", "DL", "DR", "WBL", "WBR", "DM"):
            put("Tackling", "Ease Off Tackles")
        if pos in ("DC", "DM") and v.marking >= 14 and tactical_style == "Defensive Solidity":
            put("Marking", "Mark Tighter")
        if slot.oop_role.startswith(("Pressing ", "Stopping ")) or slot.oop_role == "Centre Forward":
            if v.stamina <= 10:
                put("Trigger Press", "Less Often")
            elif v.work_rate >= 15:
                put("Trigger Press", "More Often")

        return [f"{k}: {s}" for k, s in tiles.items()] or [NO_PI_TWEAKS]
