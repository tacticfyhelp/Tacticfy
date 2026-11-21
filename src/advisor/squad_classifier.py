"""Classifies squad players into Keep, Loan Out, Sell High, and Offload categories."""

from statistics import median
from typing import List, Set

from src.engine.role_evaluator import RoleEvaluator
from src.models.player import Player
from src.models.tactics import LineupResult, PlayerClassification

# A squad usually carries about this many senior players worth keeping; CA rank inside this band
# protects a player from "Offload" even when the chosen formation has no slot for them.
CORE_SQUAD_SIZE = 22
MIN_KEEPERS = 3


def has_real_finances(squad: List[Player]) -> bool:
    """Return False when every player shares one wage/value pair (e.g. unmapped live-RAM defaults).

    In that case wage and market value carry no information and must not drive advice.
    """
    if len(squad) < 2:
        return True
    return len({(p.wage_weekly, p.market_value) for p in squad}) > 1


def _percentile(values: List[int], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


class SquadClassifier:
    """Evaluates every player in the squad for retention, loaning, or selling."""

    def __init__(self, evaluator: RoleEvaluator) -> None:
        self.evaluator = evaluator

    @staticmethod
    def _is_prospect(p: Player) -> bool:
        """Young player with real headroom and at least acceptable mentality."""
        if p.age <= 21:
            return p.pa_ca_delta >= 15 and p.hidden.professionalism >= 10 and p.hidden.ambition >= 9
        # 22-23 year-olds still develop, but only with a big gap and a good mentality.
        return p.age <= 23 and p.pa_ca_delta >= 20 and p.hidden.professionalism >= 12 and p.hidden.ambition >= 11

    def classify(self, squad: List[Player], lineup: LineupResult) -> List[PlayerClassification]:
        """Classify every squad member with actionable transfer/loan guidance."""
        starter_ids = {a.player.player_id for a in lineup.best_xi}
        backup_ids = {a.player.player_id for a in lineup.backup_xi}
        finances_known = has_real_finances(squad)
        avg_wage = sum(p.wage_weekly for p in squad) / max(1, len(squad))
        cas = [p.hidden.ca for p in squad]
        median_ca = median(cas) if cas else 0
        # "False potential" bar scales with squad level: top-squad CA + 15, never above 148.
        sell_high_pa = min(148.0, _percentile(cas, 0.80) + 15)
        ordered = sorted(squad, key=lambda x: -x.hidden.ca)
        ca_rank = {p.player_id: i for i, p in enumerate(ordered)}
        # Ties at the cut-off are all kept (CA >= the 22nd-best CA).
        core_ca_cutoff = ordered[min(CORE_SQUAD_SIZE, len(ordered)) - 1].hidden.ca if ordered else 0

        # Goalkeeper depth: starters/backups first, then the best remaining keepers up to MIN_KEEPERS.
        keepers = sorted((p for p in squad if p.is_gk), key=lambda x: -x.hidden.ca)
        kept_gk_ids: Set[int] = {p.player_id for p in keepers if p.player_id in starter_ids | backup_ids}
        for gk in keepers:
            if len(kept_gk_ids) >= MIN_KEEPERS:
                break
            kept_gk_ids.add(gk.player_id)

        results: List[PlayerClassification] = []
        for p in squad:
            best_ip_role, best_ip_score = self.evaluator.best_overall_ip_role(p)
            best_oop_role, best_oop_score = self.evaluator.best_overall_oop_role(p)
            reasons: List[str] = []
            physical_decline = p.age >= 30 and (p.visible.pace <= 10 or p.visible.stamina <= 10)
            prospect = self._is_prospect(p)

            if p.player_id in starter_ids:
                category = "Core Starter (Keep)"
                color = "#22c55e"
                reasons.append(f"Selected in optimal Best XI ({lineup.formation_name}).")
                if p.hidden.important_matches >= 14:
                    reasons.append(f"Big-game performer (Imp. Matches {p.hidden.important_matches}).")
            elif p.age <= 23 and p.hidden.pa >= sell_high_pa and (
                p.hidden.professionalism <= 9
                or p.hidden.injury_proneness >= 14
                or p.hidden.ambition <= 8
            ):
                category = "Sell High (False Potential)"
                color = "#f97316"
                if p.hidden.professionalism <= 9:
                    reasons.append(f"Low Professionalism ({p.hidden.professionalism}) blocks reaching PA {p.hidden.pa}.")
                if p.hidden.ambition <= 8:
                    reasons.append(f"Low Ambition ({p.hidden.ambition}) limits development.")
                if p.hidden.injury_proneness >= 14:
                    reasons.append(f"High Injury Proneness ({p.hidden.injury_proneness}) creates reliability risk.")
                if finances_known:
                    reasons.append(f"Cash in near current market value (${p.market_value:,}).")
                else:
                    reasons.append(f"Sell while age {p.age} and PA {p.hidden.pa} still drive the valuation.")
            elif p.player_id in backup_ids:
                if finances_known:
                    offload = physical_decline and p.hidden.consistency <= 10 and p.wage_weekly > avg_wage * 1.15
                    offload_reason = "Aging physical decline + high wage relative to squad average."
                else:
                    offload = physical_decline and p.hidden.consistency <= 10 and p.hidden.ca < median_ca
                    offload_reason = (
                        f"Aging physical decline, low Consistency ({p.hidden.consistency}) "
                        f"and CA {p.hidden.ca} below squad median ({median_ca:g})."
                    )
                if offload:
                    category = "Sell / Offload"
                    color = "#ef4444"
                    reasons.append(offload_reason)
                else:
                    # Second XI players are the depth chart: never send them away automatically.
                    category = "Rotation / Sub (Keep)"
                    color = "#a3e635"
                    reasons.append("Key Second XI depth option with solid tactical fit.")
                    if prospect:
                        reasons.append(
                            f"Upside CA {p.hidden.ca} -> PA {p.hidden.pa}: loan only if replacement cover is found."
                        )
            elif prospect:
                category = "Loan Out (Development)"
                color = "#38bdf8"
                reasons.append(
                    f"High upside (CA {p.hidden.ca} -> PA {p.hidden.pa}, +{p.pa_ca_delta} headroom)."
                )
                if p.hidden.professionalism >= 12 and p.hidden.ambition >= 12:
                    reasons.append(
                        f"Strong mentality (Prof {p.hidden.professionalism}, Amb {p.hidden.ambition}) needs regular starts."
                    )
                else:
                    reasons.append(
                        f"Needs senior minutes; monitor mentality (Prof {p.hidden.professionalism}, "
                        f"Amb {p.hidden.ambition})."
                    )
            elif p.is_gk and p.player_id in kept_gk_ids:
                category = "Rotation / Sub (Keep)"
                color = "#a3e635"
                reasons.append(f"Third-choice goalkeeper cover (CA {p.hidden.ca}).")
            elif p.hidden.ca >= core_ca_cutoff and not physical_decline and not p.is_gk:
                category = "Rotation / Sub (Keep)"
                color = "#a3e635"
                reasons.append(
                    f"Top-{CORE_SQUAD_SIZE} squad quality (CA {p.hidden.ca}, rank {ca_rank[p.player_id] + 1}) "
                    f"but no slot in {lineup.formation_name}; best fit {best_ip_role} ({best_ip_score:.1f})."
                )
            else:
                category = "Sell / Offload"
                color = "#ef4444"
                if finances_known and p.wage_weekly > avg_wage:
                    reasons.append(f"High wage (${p.wage_weekly:,}/wk) outside top 22.")
                if physical_decline:
                    reasons.append("Declining physicals (Pace/Stamina <= 10).")
                if p.hidden.ca < median_ca:
                    reasons.append(f"CA {p.hidden.ca} below squad median ({median_ca:g}).")
                if p.pa_ca_delta < 10:
                    reasons.append(f"Limited headroom (PA {p.hidden.pa}, +{p.pa_ca_delta}).")
                if p.hidden.injury_proneness >= 14:
                    reasons.append(f"High Injury Proneness ({p.hidden.injury_proneness}).")
                if p.hidden.consistency <= 8:
                    reasons.append(f"Low Consistency ({p.hidden.consistency}).")
                if p.age <= 21 and p.hidden.professionalism < 10:
                    reasons.append(f"Low Professionalism ({p.hidden.professionalism}) for a young player.")
                reasons.append("Surplus to Best XI and Second XI requirements.")

            results.append(
                PlayerClassification(
                    player=p,
                    category=category,
                    badge_color=color,
                    best_ip_role=best_ip_role,
                    best_ip_score=best_ip_score,
                    best_oop_role=best_oop_role,
                    best_oop_score=best_oop_score,
                    reasons=reasons,
                )
            )
        return results
