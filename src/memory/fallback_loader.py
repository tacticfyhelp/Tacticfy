"""Fallback squad loaders: FM HTML/RTF/CSV view parser and realistic 26-player mock squad."""

import csv
from pathlib import Path
import random
from typing import Dict, List

from bs4 import BeautifulSoup

from src.models.player import Player, PlayerHiddenAttributes, PlayerVisibleAttributes


def _make_player(
    pid: int,
    name: str,
    age: int,
    positions: List[str],
    ca: int,
    pa: int,
    wage: int,
    value: int,
    is_gk: bool = False,
    prof: int = 14,
    amb: int = 13,
    imp: int = 13,
    pres: int = 13,
    cons: int = 13,
    inj: int = 6,
    overrides: Dict[str, int] | None = None,
) -> Player:
    """Create a realistic Player with position-appropriate baseline attributes."""
    base = max(6, min(18, round(ca / 10.5)))
    vis = PlayerVisibleAttributes(
        corners=max(5, base - 2),
        crossing=max(5, base - 1),
        dribbling=max(5, base),
        finishing=max(5, base - 2),
        first_touch=max(6, base + 1),
        free_kick_taking=max(5, base - 2),
        heading=max(5, base - 1),
        long_shots=max(5, base - 1),
        long_throws=max(5, base - 3),
        marking=max(5, base - 1),
        passing=max(6, base + 1),
        penalty_taking=max(5, base - 1),
        tackling=max(5, base - 1),
        technique=max(6, base + 1),
        aggression=max(6, base),
        anticipation=max(6, base + 1),
        bravery=max(6, base),
        composure=max(6, base + 1),
        concentration=max(6, base),
        decisions=max(6, base + 1),
        determination=max(8, base + 1),
        flair=max(5, base),
        leadership=max(5, base - 1),
        off_the_ball=max(6, base),
        positioning=max(6, base),
        teamwork=max(6, base + 1),
        vision=max(6, base),
        work_rate=max(7, base + 1),
        acceleration=max(6, base + 1),
        agility=max(6, base),
        balance=max(6, base),
        jumping_reach=max(5, base - 1),
        natural_fitness=max(7, base + 1),
        pace=max(6, base + 1),
        stamina=max(7, base + 1),
        strength=max(6, base),
    )
    if is_gk:
        vis.reflexes = min(19, base + 3)
        vis.handling = min(19, base + 2)
        vis.one_on_ones = min(19, base + 2)
        vis.command_of_area = min(19, base + 2)
        vis.aerial_reach = min(19, base + 2)
        vis.kicking = min(19, base + 1)
        vis.rushing_out = min(19, base + 1)
        vis.communication = min(19, base + 1)
        vis.finishing = 3
        vis.tackling = 4

    if overrides:
        for k, v in overrides.items():
            if hasattr(vis, k):
                setattr(vis, k, max(1, min(20, v)))

    fam = {p: 20 for p in positions}
    hidden = PlayerHiddenAttributes(
        ca=ca,
        pa=pa,
        consistency=cons,
        important_matches=imp,
        injury_proneness=inj,
        professionalism=prof,
        ambition=amb,
        pressure=pres,
        temperament=13,
        versatility=12,
        adaptability=12,
        loyalty=12,
        dirtiness=7,
    )
    return Player(
        player_id=pid,
        name=name,
        age=age,
        nationality="International",
        positions=positions,
        position_familiarity=fam,
        preferred_foot="Right" if pid % 3 != 0 else "Left",
        wage_weekly=wage,
        market_value=value,
        is_gk=is_gk,
        visible=vis,
        hidden=hidden,
    )


def generate_sample_squad() -> List[Player]:
    """Generate a realistic 26-player FM27 squad for immediate offline testing."""
    return [
        # Goalkeepers (2)
        _make_player(1, "Lucas Chevalier", 24, ["GK"], 148, 162, 42000, 28000000, is_gk=True, imp=15, pres=15, cons=15, overrides={"reflexes": 16, "handling": 15, "kicking": 15, "one_on_ones": 16}),
        _make_player(2, "Jonas Urbig", 22, ["GK"], 124, 152, 16000, 8500000, is_gk=True, prof=15, amb=14, overrides={"reflexes": 14, "kicking": 14}),

        # Center-Backs (5)
        _make_player(3, "Piero Hincapie", 24, ["DC", "DL"], 154, 166, 65000, 42000000, imp=15, pres=14, cons=15, overrides={"tackling": 16, "marking": 15, "pace": 16, "acceleration": 16, "passing": 14, "anticipation": 15}),
        _make_player(4, "Murillo Santos", 23, ["DC"], 149, 164, 52000, 36000000, imp=14, pres=14, cons=14, overrides={"tackling": 16, "pace": 16, "acceleration": 15, "strength": 16, "passing": 14}),
        _make_player(5, "Ousmane Diomande", 22, ["DC"], 140, 158, 34000, 22000000, imp=13, pres=13, cons=13, overrides={"tackling": 15, "marking": 14, "pace": 15, "jumping_reach": 15}),
        _make_player(6, "Tomas Araujo", 23, ["DC"], 133, 146, 22000, 12000000, overrides={"tackling": 14, "passing": 14, "pace": 14}),
        _make_player(7, "veteran Stefan Bell", 33, ["DC"], 118, 125, 48000, 1200000, cons=8, inj=13, overrides={"pace": 8, "acceleration": 8, "stamina": 9, "tackling": 13, "marking": 13}),

        # Full-Backs / Wing-Backs (4)
        _make_player(8, "Milos Kerkez", 22, ["DL", "WBL"], 144, 160, 38000, 26000000, imp=14, pres=13, overrides={"pace": 17, "acceleration": 17, "stamina": 16, "work_rate": 16, "crossing": 14, "tackling": 13}),
        _make_player(9, "Malo Gusto", 23, ["DR", "WBR"], 147, 162, 46000, 32000000, imp=14, pres=14, overrides={"pace": 16, "acceleration": 16, "crossing": 15, "stamina": 16, "tackling": 14, "passing": 14}),
        _make_player(10, "Lewis Hall", 21, ["DL", "MC", "DM"], 131, 155, 20000, 14000000, prof=15, amb=14, overrides={"passing": 15, "first_touch": 15, "vision": 14, "decisions": 14, "pace": 14}),
        _make_player(11, "Kiliann Sildillia", 23, ["DR", "DC"], 127, 138, 18000, 9000000, overrides={"tackling": 14, "marking": 13, "pace": 14, "stamina": 14}),

        # Defensive & Central Midfielders (6)
        _make_player(12, "Joao Neves", 21, ["DM", "MC"], 156, 178, 62000, 58000000, prof=17, amb=16, imp=16, pres=16, cons=16, overrides={"tackling": 16, "passing": 16, "work_rate": 18, "stamina": 17, "decisions": 16, "anticipation": 16, "composure": 16}),
        _make_player(13, "Alan Varela", 24, ["DM", "MC"], 145, 156, 40000, 29000000, imp=15, pres=15, cons=15, overrides={"positioning": 16, "tackling": 15, "passing": 15, "decisions": 15, "concentration": 15, "anticipation": 15}),
        _make_player(14, "Kobbie Mainoo", 21, ["MC", "DM"], 146, 170, 44000, 38000000, prof=15, amb=15, imp=15, pres=15, overrides={"dribbling": 16, "first_touch": 16, "composure": 16, "passing": 15, "work_rate": 15, "stamina": 15}),
        _make_player(15, "Warren Zaire-Emery", 20, ["MC", "DM"], 148, 176, 48000, 45000000, prof=16, amb=16, imp=15, pres=15, overrides={"stamina": 17, "work_rate": 17, "passing": 15, "tackling": 14, "pace": 15, "off_the_ball": 15}),
        _make_player(16, "Sverre Nypan", 19, ["MC", "AMC"], 118, 165, 9000, 7500000, prof=16, amb=15, overrides={"passing": 14, "vision": 15, "technique": 14, "first_touch": 14}),
        _make_player(17, "Rayan Cherki", 22, ["AMC", "AMR"], 136, 166, 36000, 27000000, prof=7, amb=8, inj=10, imp=9, pres=9, cons=8, overrides={"dribbling": 17, "flair": 18, "technique": 17, "vision": 16, "work_rate": 7, "stamina": 9}),

        # Attacking Midfielders & Wingers (5)
        _make_player(18, "Arda Guler", 21, ["AMC", "AMR"], 151, 175, 55000, 50000000, prof=15, amb=16, imp=15, pres=15, overrides={"passing": 17, "vision": 17, "technique": 17, "first_touch": 17, "flair": 16, "dribbling": 15, "finishing": 14}),
        _make_player(19, "Nico Williams", 23, ["AML", "AMR"], 155, 169, 72000, 55000000, imp=15, pres=14, cons=14, overrides={"pace": 18, "acceleration": 18, "dribbling": 17, "crossing": 15, "off_the_ball": 15, "finishing": 13}),
        _make_player(20, "Savinho Moreira", 22, ["AMR", "AML"], 149, 167, 50000, 44000000, imp=14, pres=14, cons=14, overrides={"dribbling": 17, "acceleration": 17, "pace": 16, "passing": 15, "vision": 15, "finishing": 13}),
        _make_player(21, "Roony Bardghji", 20, ["AMR", "AMC"], 121, 158, 11000, 8000000, prof=15, amb=15, overrides={"dribbling": 14, "finishing": 13, "acceleration": 15, "technique": 14}),
        _make_player(22, "Ansu Fati", 23, ["AML", "ST"], 134, 156, 68000, 21000000, prof=11, amb=11, inj=17, imp=10, pres=9, overrides={"finishing": 14, "dribbling": 15, "acceleration": 14, "stamina": 10}),

        # Strikers (4)
        _make_player(23, "Benjamin Sesko", 23, ["ST"], 153, 172, 66000, 52000000, imp=14, pres=14, cons=14, overrides={"finishing": 16, "pace": 17, "acceleration": 16, "jumping_reach": 16, "heading": 15, "off_the_ball": 16, "composure": 15}),
        _make_player(24, "Karim Konate", 22, ["ST"], 137, 156, 26000, 18000000, overrides={"pace": 16, "acceleration": 16, "finishing": 14, "off_the_ball": 15, "work_rate": 14}),
        _make_player(25, "Francesco Camarda", 18, ["ST"], 114, 168, 6500, 6000000, prof=16, amb=16, overrides={"finishing": 14, "off_the_ball": 14, "anticipation": 14, "composure": 13}),
        _make_player(26, "Danny Ings", 33, ["ST"], 116, 128, 54000, 900000, cons=8, inj=16, overrides={"pace": 8, "acceleration": 8, "stamina": 8, "finishing": 14, "off_the_ball": 13}),
    ]


def _safe_int(val: str, default: int = 10) -> int:
    cleaned = "".join(ch for ch in str(val) if ch.isdigit())
    return int(cleaned) if cleaned else default


def _parse_rows_to_players(headers: List[str], rows: List[List[str]]) -> List[Player]:
    norm_headers = [h.strip().lower() for h in headers]
    players: List[Player] = []
    rng = random.Random(42)

    for idx, row in enumerate(rows, start=1):
        if len(row) < 2:
            continue
        data = {norm_headers[i]: row[i].strip() for i in range(min(len(norm_headers), len(row)))}
        name = data.get("name") or data.get("player") or f"Imported Player {idx}"
        if not name or name == "-":
            continue
        age = _safe_int(data.get("age", "23"), 23)
        pos_raw = data.get("position") or data.get("pos") or "MC"
        positions = [p.strip().upper() for p in pos_raw.replace("/", ",").split(",") if p.strip()] or ["MC"]
        ca = _safe_int(data.get("ca", "125"), 125)
        pa = _safe_int(data.get("pa", str(max(ca, 140))), max(ca, 140))
        wage = _safe_int(data.get("wage", "15000"), 15000)
        val = _safe_int(data.get("value", "5000000"), 5000000)
        is_gk = "GK" in positions

        overrides: Dict[str, int] = {}
        for attr in (
            "pace", "acceleration", "stamina", "work_rate", "finishing", "passing",
            "tackling", "marking", "positioning", "decisions", "anticipation", "dribbling",
            "crossing", "vision", "composure", "first_touch", "reflexes", "handling",
        ):
            if attr in data:
                overrides[attr] = _safe_int(data[attr], 11)

        players.append(
            _make_player(
                pid=idx,
                name=name,
                age=age,
                positions=positions,
                ca=ca,
                pa=pa,
                wage=wage,
                value=val,
                is_gk=is_gk,
                prof=_safe_int(data.get("professionalism", str(rng.randint(10, 16))), 12),
                amb=_safe_int(data.get("ambition", str(rng.randint(10, 16))), 12),
                imp=_safe_int(data.get("important matches", str(rng.randint(10, 16))), 12),
                pres=_safe_int(data.get("pressure", str(rng.randint(10, 16))), 12),
                cons=_safe_int(data.get("consistency", str(rng.randint(10, 16))), 12),
                inj=_safe_int(data.get("injury proneness", str(rng.randint(4, 12))), 7),
                overrides=overrides,
            )
        )
    return players


def load_squad_from_file(file_path: Path) -> List[Player]:
    """Import an exported FM27 HTML, RTF, or CSV squad view."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Squad export file not found: {path}")

    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".csv":
        reader = csv.reader(raw_text.splitlines())
        all_rows = list(reader)
        if not all_rows:
            return []
        return _parse_rows_to_players(all_rows[0], all_rows[1:])

    if suffix in (".html", ".htm"):
        soup = BeautifulSoup(raw_text, "html.parser")
        table = soup.find("table")
        if not table:
            return []
        trs = table.find_all("tr")
        if not trs:
            return []
        headers = [cell.get_text(strip=True) for cell in trs[0].find_all(["th", "td"])]
        rows = [[cell.get_text(strip=True) for cell in tr.find_all("td")] for tr in trs[1:]]
        return _parse_rows_to_players(headers, rows)

    if suffix == ".rtf":
        lines = [ln.strip() for ln in raw_text.splitlines() if "|" in ln]
        if len(lines) >= 2:
            headers = [h.strip() for h in lines[0].strip("|").split("|")]
            rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines[2:] if "---" not in ln]
            return _parse_rows_to_players(headers, rows)

    return []
