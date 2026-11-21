"""Unit tests for SquadClassifier and WeakestLinkAnalyzer."""

from pathlib import Path
import unittest

from src.advisor.squad_classifier import SquadClassifier
from src.advisor.weakest_link import WeakestLinkAnalyzer
from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.memory.fallback_loader import generate_sample_squad


class TestSquadAdvisor(unittest.TestCase):
    """Validate Keep/Loan/Sell High/Offload classification and Weakest Link profiling."""

    def setUp(self) -> None:
        cfg_dir = Path(__file__).resolve().parent.parent / "config"
        self.evaluator = RoleEvaluator(
            cfg_dir / "roles_in_possession.json",
            cfg_dir / "roles_out_possession.json",
        )
        self.optimizer = SynergyOptimizer(cfg_dir / "formations.json", self.evaluator)
        self.squad = generate_sample_squad()
        self.lineup = self.optimizer.optimize(self.squad, tactical_style="Balanced Tactical Meta")

    def test_classification_buckets(self) -> None:
        classifier = SquadClassifier(self.evaluator)
        classified = classifier.classify(self.squad, self.lineup)
        self.assertEqual(len(classified), len(self.squad))

        by_name = {c.player.name: c for c in classified}
        # Cherki has low Professionalism (7) -> Sell High (False Potential)
        self.assertEqual(by_name["Rayan Cherki"].category, "Sell High (False Potential)")
        # Camarda / Nypan have high PA delta and high Professionalism -> Loan Out (Development)
        self.assertEqual(by_name["Francesco Camarda"].category, "Loan Out (Development)")
        # Aging high-wage veterans -> Sell / Offload
        self.assertEqual(by_name["Danny Ings"].category, "Sell / Offload")

    def test_weakest_link_report(self) -> None:
        analyzer = WeakestLinkAnalyzer(self.evaluator)
        report = analyzer.analyze(self.lineup)
        self.assertTrue(report.weakest_slot_id)
        self.assertTrue(report.minimum_attributes)
        self.assertIn("important_matches", report.minimum_attributes)


if __name__ == "__main__":
    unittest.main()
