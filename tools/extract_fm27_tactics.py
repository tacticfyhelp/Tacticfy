"""Extract the official FM27 tactics vocabulary from the installed game and print it.

Sources (all read-only, nothing in the game folder is modified):
  * fm_Data/StreamingAssets/aa/.../ui-staticdataentries_assets_all.bundle
      RolesData                 -> the In / Out of Possession roles the tactics UI offers
      TacticTeamInstructionData -> every team instruction and its option order
      GenericTacticData         -> which phase each team instruction belongs to
      PlayerInstructionEntry    -> player instruction tiles and their options (PI_* ids)
  * fm_Data/il2cpp_data/Metadata/global-metadata.dat
      PlayerInstruction enum    -> names for the PI_* option ids
  * data/game_simulation/templates/user_folder/languages/example.ltf
      English source strings    -> exact display labels (each label is checked to exist)

Reading the Unity bundle needs UnityPy (pip install UnityPy). Without it the script still prints
the role names and labels it can verify from the language file alone.

Usage:
    python tools/extract_fm27_tactics.py            # print lists
    python tools/extract_fm27_tactics.py --write    # also write config/fm27_tactics_reference.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_PATH = PROJECT_ROOT / "config" / "fm27_tactics_reference.json"
DEFAULT_INSTALL = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Football Manager 27")

PHASES = {  # GenericTacticData TeamInstructionPhaseID -> FM27 tactics screen section
    0: ("In Possession", "Overview"),
    3: ("In Possession", "Build-Up"),
    2: ("In Possession", "Progression"),
    1: ("In Possession", "Final Third"),
    4: ("Out of Possession", "Overview"),
    5: ("Out of Possession", "High Press"),
    6: ("Out of Possession", "Mid Block"),
    7: ("Out of Possession", "Low Block"),
}

# Team instruction asset name -> (display title, option labels in the asset's option order).
# Every label below is verified against example.ltf when the script runs.
TEAM_INSTRUCTION_LABELS: Dict[str, tuple] = {
    "PassingDirectness": ("Directness", ["Much Shorter", "Shorter", "Standard", "More Direct", "Much More Direct"]),
    "Tempo": ("Tempo", ["Much Lower", "Lower", "Standard", "Higher", "Much Higher"]),
    "AttackingWidth": ("Team Width", ["Much Narrower", "Narrower", "Standard", "Wider", "Much Wider"]),
    "AttackingTransition": ("Attacking Transition", ["Hold Shape", "Standard", "Counter-Attack"]),
    "CreativeFreedom": ("Creative Freedom", ["More Disciplined", "Balanced", "More Expressive"]),
    "TimeWasting": ("Time Wasting", ["Less Often", "Standard", "More Often"]),
    "PlayForSetPieces": ("Play for Set Pieces", ["Keep Ball in Play", "Play for Set Pieces"]),
    "BuildUpStrategy": ("Build-Up Strategy", ["Play Through Press", "Balanced", "Bypass Press"]),
    "GoalKicks": ("Goal Kicks", ["Short", "Mixed", "Long"]),
    "GoalkeeperDistributionSpeed": ("GK Distribution (Speed)", ["Slow Pace Down", "Balanced", "Distribute Quickly"]),
    "GoalkeeperDistributionTarget": ("GK Distribution", [
        "Balanced", "Distribute to Centre-Backs", "Distribute To Full-Backs", "Distribute to Flanks",
        "Distribute to Playmaker", "Distribute to Target Forward", "Distribute Over Opposition Defence"]),
    "SupportingRuns": ("Supporting Runs", ["Balanced", "Underlap Left Flank", "Underlap Right Flank", "Underlap Both Flanks"]),
    "Dribbling": ("Dribbling", ["Discourage", "Standard", "Encourage"]),
    "ProgressThrough": ("Progress Through", [
        "Balanced", "Progress Through the Middle", "Progress Through Left Flank",
        "Progress Through Right Flank", "Progress Through Both Flanks"]),
    "PassReception": ("Pass Reception", ["Pass Into Feet", "Standard", "Pass Into Space"]),
    "Patience": ("Patience", ["Hit Early Crosses", "Standard", "Work Ball Into Box"]),
    "ShotsFromDistance": ("Shots from Distance", ["Discourage", "Balanced", "Encourage"]),
    "Crossing": ("Crossing Style", ["Balanced", "Floated Crosses", "Whipped Crosses", "Low Crosses"]),
    "LineOfEngagement": ("Line of Engagement", ["Low Block", "Mid Block", "High Press"]),
    "DefensiveLine": ("Defensive Line", ["Much Lower", "Lower", "Standard", "Higher", "Much Higher"]),
    "DefensiveLineBehaviour": ("Defensive Line Behaviour", ["Step Up More", "Balanced", "Drop Off More"]),
    "TriggerPress": ("Trigger Press", ["Much Less Often", "Less Often", "Standard", "More Often", "Much More Often"]),
    "DefensiveTransition": ("Defensive Transition", ["Regroup", "Standard", "Counter-Press"]),
    "Tackling": ("Tackling", ["Ease Off Tackles", "Standard", "Tackle Harder"]),
    "PressingTrap": ("Pressing Trap", ["Trap Inside", "Balanced", "Trap Outside"]),
    "PreventShortGKDistribution": ("Prevent Short GK Distribution", ["No", "Yes"]),
    "CrossEngagement": ("Cross Engagement", ["Stop Crosses", "Balanced", "Invite Crosses"]),
}

# PlayerInstructionGrouping enum -> display title; PI_* option -> display label.
PLAYER_INSTRUCTION_TITLES = {
    "AttackingWidth": "Attacking Width", "DribblingDirection": "Dribbling Direction",
    "DribblingFrequency": "Dribbling Frequency", "ForwardRuns": "Forward Runs",
    "FreedomOfMovement": "Freedom of Movement", "HoldUpBall": "Hold Up Ball", "Shooting": "Shooting",
    "PassingStrategy": "Passing Strategy", "PassingRisk": "Passing Risk", "CrossingStrategy": "Crossing Strategy",
    "CrossFrom": "Cross From", "TriggerPress": "Trigger Press", "Marking": "Marking", "Tackling": "Tackling",
    "MarkingTarget": "Marking Target", "AttackBoxSide": "Attack Box - Side", "AttackBoxDepth": "Attack Box - Depth",
}
PI_LABELS = {
    "PI_NONE": "Standard",
    "PI_STAY_WIDER": "Stay Wider", "PI_PLAY_NARROW": "Sit Narrower", "PI_MOVE_INTO_CHANNELS": "Move Into Channels",
    "PI_RUN_WIDE_WITH_BALL": "Run Wide With Ball", "PI_CUT_INSIDE_WITH_BALL": "Cut Inside With Ball",
    "PI_DRIBBLE_MORE": "Dribble More", "PI_DRIBBLE_LESS": "Dribble Less",
    "PI_GET_FORWARD_OFTEN": "Make More Runs", "PI_HOLD_POSITION": "Make Fewer Runs",
    "PI_ROAM_FROM_POSITION": "Roam From Position",
    "PI_SHOOT_MORE": "Shoot More Often", "PI_SHOOT_LESS": "Shoot Less Often",
    "PI_HOLD_UP_BALL": "Yes",
    "PI_PASS_SHORTER": "Shorter", "PI_PASS_MORE_DIRECT": "More Direct",
    "PI_TAKE_MORE_RISKS": "Take More Risks", "PI_TAKE_FEWER_RISKS": "Take Fewer Risks",
    "PI_CROSS_TO_FAR_POST": "Cross to Far Post", "PI_CROSS_TO_CENTRE": "Cross to Centre",
    "PI_CROSS_TO_NEAR_POST": "Cross to Near Post", "PI_CROSS_TO_TARGET_MAN": "Cross to Target Forward",
    "PI_CROSS_FROM_DEEP": "Cross From Deep", "PI_CROSS_FROM_BYLINE": "Byline",
    "PI_HIGHER_PRESSING_INTENSITY": "More Often", "PI_LOWER_PRESSING_INTENSITY": "Less Often",
    "PI_MARK_TIGHTER": "Mark Tighter",
    "PI_GET_STUCK_IN": "Tackle Harder", "PI_STAY_ON_FEET": "Ease Off Tackles",
    "PI_MARK_SPECIFIC_PLAYER": "Mark Specific", "PI_MARK_SPECIFIC_POSITION": "Mark Position",
    "PI_ATTACK_BOX_SIDE_CENTRE": "Centre", "PI_ATTACK_BOX_SIDE_LEFT": "Left", "PI_ATTACK_BOX_SIDE_RIGHT": "Right",
    "PI_ATTACK_BOX_SIDE_NEAR_POST": "Near Post", "PI_ATTACK_BOX_SIDE_FAR_POST": "Far Post",
    "PI_ATTACK_FRONT_ZONE": "Attack Defensive Line", "PI_ATTACK_BACK_ZONE": "Arrive Late in Box",
}
# "No" for Hold Up Ball and "Follow Tactical Position" for Freedom of Movement replace "Standard".
PI_NONE_OVERRIDE = {"HoldUpBall": "No", "FreedomOfMovement": "Follow Tactical Position"}

MENTALITIES = ["Very Defensive", "Defensive", "Cautious", "Balanced", "Positive", "Attacking", "Very Attacking"]

# Role asset ids whose English name is not a plain CamelCase split of the id.
ROLE_NAME_OVERRIDES = {
    "OPLineKeeper": "Line-Holding Goalkeeper",
    "OPWideCoverDefensiveMidfielder": "Wide Covering Defensive Midfielder",
    "OPWideCoverCentralMidfielder": "Wide Covering Central Midfielder",
    "BoxToBoxMidfielder": "Box-To-Box Midfielder",
    "BoxToBoxPlaymaker": "Box-To-Box Playmaker",
}


# ----------------------------------------------------------------------------------- locating
def find_install() -> Path:
    try:
        import psutil

        for proc in psutil.process_iter(["name", "exe"]):
            if (proc.info.get("name") or "").lower() == "fm.exe" and proc.info.get("exe"):
                return Path(proc.info["exe"]).parent
    except Exception:  # noqa: BLE001 - psutil missing or access denied: fall back to Steam path
        pass
    if DEFAULT_INSTALL.exists():
        return DEFAULT_INSTALL
    raise SystemExit("FM27 installation not found (start fm.exe or edit DEFAULT_INSTALL).")


# ----------------------------------------------------------------------------------- sources
def load_ltf(install: Path) -> Dict[str, List[int]]:
    """Map every English string in example.ltf to the KEY ids that carry it."""
    path = install / "data" / "game_simulation" / "templates" / "user_folder" / "languages" / "example.ltf"
    entry = re.compile(r"^KEY-(\d+): (.*?)(?:\[COMMENT.*\])?\s*$")
    token = re.compile(r"\[%[^\]]*\]")
    strings: Dict[str, List[int]] = {}
    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            m = entry.match(line)
            if m:
                text = token.sub("", m.group(2)).strip()
                if 0 < len(text) <= 60:
                    strings.setdefault(text, []).append(int(m.group(1)))
    return strings


def load_pi_enum(install: Path) -> List[str]:
    meta = (install / "fm_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat").read_bytes()
    names = [s.decode("utf-8", "replace") for s in meta.split(b"\x00")]
    start = names.index("PI_NONE")
    out = []
    for name in names[start:]:
        if not name.startswith("PI_"):
            break
        out.append(name)
    return out


def load_assets(install: Path) -> Optional[dict]:
    try:
        import UnityPy  # noqa: F401
    except ImportError:
        return None
    import UnityPy

    bundle = install / "fm_Data" / "StreamingAssets" / "aa" / "StandaloneWindows64" / "ui-staticdataentries_assets_all.bundle"
    env = UnityPy.load(str(bundle))
    by_id = {obj.path_id: obj for obj in env.objects}

    def resolve(node, depth=0):
        if isinstance(node, dict):
            if set(node) == {"m_FileID", "m_PathID"} and node["m_FileID"] == 0 and node["m_PathID"] in by_id and depth < 4:
                child = by_id[node["m_PathID"]]
                if child.type.name == "MonoBehaviour":
                    return resolve(child.read_typetree(), depth + 1)
            return {k: resolve(v, depth) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v, depth) for v in node]
        return node

    wanted = {"RolesData", "TacticTeamInstructionData", "GenericTacticData", "PlayerInstructionEntry", "TacticMentalitiesEntry"}
    found = {}
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            tree = obj.read_typetree()
            if tree.get("m_Name") in wanted:
                found[tree["m_Name"]] = resolve(tree)
    return found


# ----------------------------------------------------------------------------------- naming
def split_camel(identifier: str) -> str:
    words = re.findall(r"[A-Z][a-z]*|[a-z]+", identifier)
    return " ".join(words)


def role_display_name(role_id: str, ltf: Dict[str, List[int]]) -> str:
    if role_id in ROLE_NAME_OVERRIDES:
        return ROLE_NAME_OVERRIDES[role_id]
    base = role_id[2:] if role_id.startswith("OP") else role_id
    plain = split_camel(base)
    want = re.sub(r"[^a-z]", "", plain.lower())
    candidates = [s for s in ltf if re.sub(r"[^a-z]", "", s.lower()) == want and len(s) < 45]
    # Prefer the Title Case UI role name (lower-case variants are "position type" prose strings),
    # then the most recent (highest KEY) spelling, e.g. "Centre-Back" over "Centre Back".
    def title_case(s: str) -> bool:
        return all(part[:1].isupper() for part in re.split(r"[ -]", s) if part)

    candidates.sort(key=lambda s: (not title_case(s), -max(ltf[s])))
    return candidates[0] if candidates else plain


def verify(label: str, ltf: Dict[str, List[int]]) -> str:
    keys = ltf.get(label)
    return f"KEY-{max(keys)}" if keys else "NOT FOUND"


# ----------------------------------------------------------------------------------- main
def build_reference(install: Path) -> dict:
    ltf = load_ltf(install)
    assets = load_assets(install)
    if assets is None:
        raise SystemExit("UnityPy is required to read the FM27 tactics bundle:  pip install UnityPy")
    pi_enum = load_pi_enum(install)

    roles = assets["RolesData"]
    ip_roles = [{"id": e["m_roleID"], "name": role_display_name(e["m_roleID"], ltf)}
                for e in roles["m_storedInPossessionDataEntryList"]]
    oop_roles = [{"id": e["m_roleID"], "name": role_display_name(e["m_roleID"], ltf)}
                 for e in roles["m_storedOutOfPossessionEntryList"]]

    ti_by_id = {e["m_instructionID"]: e for e in assets["TacticTeamInstructionData"]["m_storedDataEntryList"]}
    team_instructions = []
    for phase in assets["GenericTacticData"]["m_phasesAndTeamInstructions"]:
        section, phase_name = PHASES[phase["TeamInstructionPhaseID"]]
        for iid in phase["TeamInstructionsForPhase"]:
            entry = ti_by_id[iid]
            title, labels = TEAM_INSTRUCTION_LABELS[entry["m_Name"]]
            if len(labels) != len(entry["m_instructionOptionEntries"]):
                raise SystemExit(f"{entry['m_Name']}: game has {len(entry['m_instructionOptionEntries'])} options, "
                                 f"label table has {len(labels)} - update TEAM_INSTRUCTION_LABELS")
            team_instructions.append({"id": entry["m_Name"], "section": section, "phase": phase_name,
                                      "title": title, "options": labels})

    groupings = list(PLAYER_INSTRUCTION_TITLES)
    player_instructions = []
    for group in assets["PlayerInstructionEntry"]["m_playerInstructionGroups"]:
        gname = groupings[group["m_groupID"]]
        options = []
        for opt in group["m_playerInstructionOptionEntries"]:
            pid = pi_enum[opt["m_instructionID"]]
            options.append(PI_NONE_OVERRIDE.get(gname, "Standard") if pid == "PI_NONE" else PI_LABELS[pid])
        player_instructions.append({"id": gname, "title": PLAYER_INSTRUCTION_TITLES[gname], "options": options})

    n_mentalities = len(assets["TacticMentalitiesEntry"]["m_mentalityOptionEntries"])
    if n_mentalities != len(MENTALITIES):
        raise SystemExit(f"Game defines {n_mentalities} mentalities, expected {len(MENTALITIES)}")

    return {
        "_source": "Extracted by tools/extract_fm27_tactics.py from the installed FM27 "
                   "(ui-staticdataentries bundle + global-metadata.dat + example.ltf).",
        "in_possession_roles": ip_roles,
        "out_of_possession_roles": oop_roles,
        "team_instructions": team_instructions,
        "player_instructions": player_instructions,
        "mentalities": MENTALITIES,
        "_ltf": ltf,  # stripped before writing; used for printing verification keys
    }


def print_reference(ref: dict) -> None:
    ltf = ref["_ltf"]
    print(f"\n=== IN POSSESSION ROLES ({len(ref['in_possession_roles'])}) ===")
    for r in sorted(ref["in_possession_roles"], key=lambda r: r["name"]):
        print(f"  {r['name']:<34} [{r['id']}]  {verify(r['name'], ltf)}")
    print(f"\n=== OUT OF POSSESSION ROLES ({len(ref['out_of_possession_roles'])}) ===")
    for r in sorted(ref["out_of_possession_roles"], key=lambda r: r["name"]):
        print(f"  {r['name']:<38} [{r['id']}]  {verify(r['name'], ltf)}")
    print(f"\n=== TEAM INSTRUCTIONS ({len(ref['team_instructions'])} tiles) ===")
    current = None
    for ti in ref["team_instructions"]:
        header = f"{ti['section']} - {ti['phase']}"
        if header != current:
            print(f"\n  [{header}]")
            current = header
        opts = ", ".join(f"{o}" + ("" if o in ltf else " (!)") for o in ti["options"])
        print(f"    {ti['title']:<30} {verify(ti['title'], ltf):<11} -> {opts}")
    print(f"\n=== PLAYER INSTRUCTION TILES ({len(ref['player_instructions'])}) ===")
    for pi in ref["player_instructions"]:
        opts = ", ".join(f"{o}" + ("" if o in ltf else " (!)") for o in pi["options"])
        print(f"    {pi['title']:<22} {verify(pi['title'], ltf):<11} -> {opts}")
    print(f"\n=== MENTALITIES ===\n    {', '.join(ref['mentalities'])}")
    missing = [o for ti in ref["team_instructions"] for o in [ti["title"], *ti["options"]] if o not in ltf]
    missing += [o for pi in ref["player_instructions"] for o in [pi["title"], *pi["options"]] if o not in ltf]
    missing += [r["name"] for r in ref["in_possession_roles"] + ref["out_of_possession_roles"] if r["name"] not in ltf]
    print(f"\nLabels not found verbatim in example.ltf: {sorted(set(missing)) or 'none'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="write config/fm27_tactics_reference.json")
    parser.add_argument("--install", type=Path, default=None, help="FM27 install folder (auto-detected)")
    args = parser.parse_args()

    install = args.install or find_install()
    print(f"FM27 install: {install}")
    ref = build_reference(install)
    print_reference(ref)
    if args.write:
        out = {k: v for k, v in ref.items() if k != "_ltf"}
        REFERENCE_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nWrote {REFERENCE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
