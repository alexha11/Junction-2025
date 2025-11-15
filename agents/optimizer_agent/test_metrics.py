"""Metrics calculator for comparing optimized vs baseline performance."""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import asyncio

from .test_simulator import RollingSimulation, RollingMPCSimulator
from .explainability import LLMExplainer, ScheduleMetrics

logger = logging.getLogger(__name__)


@dataclass
class ComparisonReport:
    """Comparison report between optimized and baseline performance."""
    summary: str
    metrics: Dict[str, Any]
    key_findings: list[str]


class MetricsCalculator:
    """Calculate and compare metrics between optimized and baseline."""

    def __init__(
        self,
        simulator: RollingMPCSimulator,
        llm_explainer: Optional[LLMExplainer] = None,
    ):
        """Initialize metrics calculator.
        
        Args:
            simulator: RollingMPCSimulator instance
            llm_explainer: Optional LLM explainer for generating explanations
        """
        self.simulator = simulator
        self.llm_explainer = llm_explainer

    def generate_comparison_report(
        self,
        simulation: RollingSimulation,
        comparison_metrics: Dict[str, Any],
    ) -> ComparisonReport:
        """Generate formatted comparison report.
        
        Args:
            simulation: RollingSimulation results
            comparison_metrics: Metrics from compare_with_baseline()
        
        Returns:
            ComparisonReport with formatted summary
        """
        energy_metrics = comparison_metrics.get('total_energy_kwh', {})
        cost_metrics = comparison_metrics.get('total_cost_eur', {})
        violation_metrics = comparison_metrics.get('l1_violations', {})
        smoothness_metrics = comparison_metrics.get('outflow_smoothness', {})
        specific_energy_metrics = comparison_metrics.get('specific_energy_kwh_m3', {})
        
        # Generate summary text
        summary_lines = [
            "=" * 70,
            "OPTIMIZATION TEST RESULTS - BASELINE COMPARISON",
            "=" * 70,
            "",
            f"Simulation Period: {simulation.start_time.strftime('%Y-%m-%d %H:%M')} to {simulation.end_time.strftime('%Y-%m-%d %H:%M')}",
            f"Total Optimization Steps: {len(simulation.results)}",
            "",
            "ENERGY CONSUMPTION:",
            f"  Baseline:     {energy_metrics.get('baseline', 0.0):>12.2f} kWh",
            f"  Optimized:    {energy_metrics.get('optimized', 0.0):>12.2f} kWh",
            f"  Savings:      {energy_metrics.get('savings_kwh', 0.0):>12.2f} kWh ({energy_metrics.get('savings_percent', 0.0):>5.2f}%)",
            "",
            "COST:",
            f"  Baseline:     {cost_metrics.get('baseline', 0.0):>12.2f} EUR",
            f"  Optimized:    {cost_metrics.get('optimized', 0.0):>12.2f} EUR",
            f"  Savings:      {cost_metrics.get('savings_eur', 0.0):>12.2f} EUR ({cost_metrics.get('savings_percent', 0.0):>5.2f}%)",
            "",
            "CONSTRAINT VIOLATIONS (L1 bounds):",
            f"  Baseline:     {violation_metrics.get('baseline', 0):>12} violations",
            f"  Optimized:    {violation_metrics.get('optimized', 0):>12} violations",
            f"  Max violation (optimized): {violation_metrics.get('optimized_max_violation', 0.0):>8.4f} m",
            f"  Max violation (baseline):  {violation_metrics.get('baseline_max_violation', 0.0):>8.4f} m",
            "",
            "OUTFLOW SMOOTHNESS (Variance):",
            f"  Baseline:     {smoothness_metrics.get('baseline_variance', 0.0):>12.6f}",
            f"  Optimized:    {smoothness_metrics.get('optimized_variance', 0.0):>12.6f}",
            f"  Improvement:  {smoothness_metrics.get('improvement_percent', 0.0):>11.2f}%",
            "",
            "SPECIFIC ENERGY (kWh/m³):",
            f"  Baseline:     {specific_energy_metrics.get('baseline', 0.0):>12.6f} kWh/m³",
            f"  Optimized:    {specific_energy_metrics.get('optimized', 0.0):>12.6f} kWh/m³",
            f"  Improvement:  {specific_energy_metrics.get('improvement_percent', 0.0):>11.2f}%",
            "",
        ]
        
        # Add pump operating hours comparison
        pump_hours = comparison_metrics.get('pump_operating_hours', {})
        optimized_hours = pump_hours.get('optimized', {})
        baseline_hours = pump_hours.get('baseline', {})
        
        if optimized_hours or baseline_hours:
            summary_lines.extend([
                "PUMP OPERATING HOURS:",
            ])
            
            # Get all pump IDs - include ALL pumps from optimizer, not just ones that were used
            all_pumps_from_results = set(list(optimized_hours.keys()) + list(baseline_hours.keys()))
            
            # Get all pump IDs from optimizer configuration (to include pumps that were never used)
            all_pumps_from_optimizer = set()
            if hasattr(self.simulator, 'optimizer') and hasattr(self.simulator.optimizer, 'pumps'):
                all_pumps_from_optimizer = set(self.simulator.optimizer.pumps.keys())
            
            # Combine both sets to ensure all pumps are shown (even if they have 0 hours)
            all_pumps = all_pumps_from_results | all_pumps_from_optimizer
            
            for pump_id in sorted(all_pumps):
                opt_hours = optimized_hours.get(pump_id, 0.0)
                base_hours = baseline_hours.get(pump_id, 0.0)
                diff = opt_hours - base_hours
                
                # Calculate percentage change (handle division by zero)
                if base_hours > 0:
                    diff_pct = (diff / base_hours * 100.0)
                    diff_pct_str = f"{diff_pct:>5.1f}"
                elif opt_hours > 0:
                    # Baseline is 0 but optimized > 0: show as "N/A"
                    diff_pct_str = "N/A"
                else:
                    # Both are 0: show as 0.0%
                    diff_pct_str = "0.0"
                
                summary_lines.append(
                    f"  {pump_id}:  Baseline={base_hours:>6.2f}h, Optimized={opt_hours:>6.2f}h, Diff={diff:>6.2f}h ({diff_pct_str:>5s}%)"
                )
            summary_lines.append("")
        
        summary_lines.append("=" * 70)
        
        summary = "\n".join(summary_lines)
        
        # Generate key findings
        key_findings = []
        
        energy_savings_pct = energy_metrics.get('savings_percent', 0.0)
        if energy_savings_pct > 0:
            key_findings.append(
                f"✓ Energy reduction: {energy_savings_pct:.2f}% ({energy_metrics.get('savings_kwh', 0.0):.2f} kWh saved)"
            )
        elif energy_savings_pct < 0:
            key_findings.append(
                f"⚠ Energy increase: {abs(energy_savings_pct):.2f}% ({abs(energy_metrics.get('savings_kwh', 0.0)):.2f} kWh additional)"
            )
        
        cost_savings_pct = cost_metrics.get('savings_percent', 0.0)
        if cost_savings_pct > 0:
            key_findings.append(
                f"✓ Cost reduction: {cost_savings_pct:.2f}% ({cost_metrics.get('savings_eur', 0.0):.2f} EUR saved)"
            )
        elif cost_savings_pct < 0:
            key_findings.append(
                f"⚠ Cost increase: {abs(cost_savings_pct):.2f}% ({abs(cost_metrics.get('savings_eur', 0.0)):.2f} EUR additional)"
            )
        
        opt_violations = violation_metrics.get('optimized', 0)
        base_violations = violation_metrics.get('baseline', 0)
        if opt_violations == 0 and base_violations > 0:
            key_findings.append(
                f"✓ Constraint violations: Eliminated all violations ({base_violations} in baseline)"
            )
        elif opt_violations < base_violations:
            key_findings.append(
                f"✓ Constraint violations: Reduced from {base_violations} to {opt_violations}"
            )
        elif opt_violations > 0:
            key_findings.append(
                f"⚠ Constraint violations: {opt_violations} violations (baseline: {base_violations})"
            )
        else:
            key_findings.append(
                f"✓ Constraint violations: None (same as baseline)"
            )
        
        smoothness_improvement = smoothness_metrics.get('improvement_percent', 0.0)
        if smoothness_improvement > 0:
            key_findings.append(
                f"✓ Outflow smoothness: Improved by {smoothness_improvement:.2f}%"
            )
        
        spec_energy_improvement = specific_energy_metrics.get('improvement_percent', 0.0)
        if spec_energy_improvement > 0:
            key_findings.append(
                f"✓ Specific energy: Improved by {spec_energy_improvement:.2f}%"
            )
        
        # Try to generate LLM explanation for the overall simulation if LLM is available
        summary_explanation = None
        if self.llm_explainer:
            logger.debug("LLM: Generating explanation for overall simulation results")
            try:
                # Create metrics for overall simulation
                overall_metrics = ScheduleMetrics(
                    total_energy_kwh=energy_metrics.get('optimized', 0.0),
                    total_cost_eur=cost_metrics.get('optimized', 0.0),
                    avg_l1_m=sum(simulation.optimized_l1_trajectory) / len(simulation.optimized_l1_trajectory) if simulation.optimized_l1_trajectory else 0.0,
                    min_l1_m=min(simulation.optimized_l1_trajectory) if simulation.optimized_l1_trajectory else 0.0,
                    max_l1_m=max(simulation.optimized_l1_trajectory) if simulation.optimized_l1_trajectory else 0.0,
                    num_pumps_used=len([h for h in pump_hours.get('optimized', {}).values() if h > 0]),
                    avg_outflow_m3_s=0.0,  # Could calculate from simulation if needed
                    # 70-100 EUR/MWh → 7-10 c/kWh
                    price_range_c_per_kwh=(7.0, 10.0),
                    risk_level="normal",
                    optimization_mode="full",
                )
                
                # Get strategic guidance (simplified - could enhance)
                strategic_guidance = ["NORMAL"] * 4
                strategy_summary = ", ".join(set(strategic_guidance))
                logger.info(f"Strategy: {strategy_summary}")
                
                # Generate LLM explanation asynchronously
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                summary_explanation = loop.run_until_complete(
                    self.llm_explainer.generate_explanation(
                        metrics=overall_metrics,
                        strategic_guidance=strategic_guidance,
                        current_state_description=f"Simulation from {simulation.start_time} to {simulation.end_time}",
                    )
                )
                
                # Add LLM explanation to key findings if available
                if summary_explanation:
                    logger.debug(f"LLM: Successfully received summary explanation ({len(summary_explanation)} chars)")
                    logger.info(f"LLM Explanation: {summary_explanation}")
                    key_findings.append(f"\nLLM Explanation: {summary_explanation}")
            except Exception as e:
                logger.warning(f"LLM: Failed to generate explanation for simulation: {e}")
                # Silently fall back if LLM fails
        else:
            logger.info("LLM: Not configured - skipping LLM explanation for simulation")
        
        return ComparisonReport(
            summary=summary,
            metrics=comparison_metrics,
            key_findings=key_findings,
        )

