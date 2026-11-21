"""Dual-phase tactical evaluation, synergy optimization, and instruction generation."""

from src.engine.instructions_gen import InstructionsGenerator
from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer

__all__ = ["RoleEvaluator", "SynergyOptimizer", "InstructionsGenerator"]
