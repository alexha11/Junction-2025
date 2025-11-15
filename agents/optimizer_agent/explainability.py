"""LLM-based explainability for optimization schedules."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ScheduleMetrics:
    """Metrics for schedule explanation."""
    total_energy_kwh: float
    total_cost_eur: float
    avg_l1_m: float
    min_l1_m: float
    max_l1_m: float
    num_pumps_used: int
    avg_outflow_m3_s: float
    price_range_eur_mwh: tuple[float, float]
    risk_level: str
    optimization_mode: str


class LLMExplainer:
    """Generate natural language explanations using Featherless LLM."""

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "llama-3.1-8b-instruct",
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    async def generate_explanation(
        self,
        metrics: ScheduleMetrics,
        strategic_guidance: list[str],
        current_state_description: str = "",
    ) -> str:
        """Generate natural language explanation for the schedule."""
        
        # If no LLM available, return structured explanation
        if not self.api_base or not self.api_key:
            logger.debug("LLM not available: missing API credentials")
            return self._generate_fallback_explanation(metrics, strategic_guidance)
        
        try:
            prompt = self._build_prompt(metrics, strategic_guidance, current_state_description)
            logger.info(f"LLM: Calling {self.api_base} with model {self.model}")
            logger.debug(f"LLM Prompt: {prompt[:200]}...")  # Log first 200 chars of prompt
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_base}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert operator assistant for wastewater pumping optimization. Provide clear, concise explanations of pump schedules in 2-3 sentences.",
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "temperature": 0.7,
                        "max_tokens": 200,
                    },
                )
                response.raise_for_status()
                data = response.json()
                explanation = data["choices"][0]["message"]["content"].strip()
                logger.info(f"LLM: Successfully received explanation ({len(explanation)} chars)")
                logger.debug(f"LLM Response: {explanation}")
                return explanation
        except httpx.TimeoutException as e:
            logger.error(f"LLM: Request timeout after 10s: {e}")
            return self._generate_fallback_explanation(metrics, strategic_guidance)
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM: HTTP error {e.response.status_code}: {e.response.text}")
            return self._generate_fallback_explanation(metrics, strategic_guidance)
        except Exception as e:
            logger.error(f"LLM: Unexpected error: {e}", exc_info=True)
            # Fallback to rule-based explanation
            return self._generate_fallback_explanation(metrics, strategic_guidance)

    def _build_prompt(
        self,
        metrics: ScheduleMetrics,
        strategic_guidance: list[str],
        current_state_description: str,
    ) -> str:
        """Build prompt for LLM."""
        guidance_summary = ", ".join(set(strategic_guidance[:4]))
        
        prompt = f"""Explain this pump schedule to an operator:

Current situation: {current_state_description if current_state_description else "Normal operations"}

Schedule metrics:
- Total energy: {metrics.total_energy_kwh:.1f} kWh
- Total cost: {metrics.total_cost_eur:.2f} EUR
- Tunnel level range: {metrics.min_l1_m:.2f} - {metrics.max_l1_m:.2f} m (safe range: 0.5-8.0 m)
- Average outflow: {metrics.avg_outflow_m3_s:.2f} m³/s
- Pumps active: {metrics.num_pumps_used}
- Price range: {metrics.price_range_eur_mwh[0]:.1f} - {metrics.price_range_eur_mwh[1]:.1f} EUR/MWh
- Risk level: {metrics.risk_level}
- Strategy guidance: {guidance_summary}

Provide a brief, clear explanation (2-3 sentences) of why this schedule was chosen, focusing on safety, cost optimization, and operational priorities."""
        
        return prompt

    def _generate_fallback_explanation(
        self,
        metrics: ScheduleMetrics,
        strategic_guidance: list[str],
    ) -> str:
        """Generate explanation without LLM."""
        parts = []
        
        # Risk-based message
        if metrics.risk_level == "critical":
            parts.append("Critical risk detected: prioritizing safety over cost.")
        elif metrics.risk_level == "high":
            parts.append("Elevated risk: balancing safety and efficiency.")
        elif metrics.risk_level == "low":
            parts.append("Low risk conditions: optimizing for cost efficiency.")
        else:
            parts.append("Normal operations: balanced optimization.")
        
        # Price-based message
        price_avg = (metrics.price_range_eur_mwh[0] + metrics.price_range_eur_mwh[1]) / 2
        if price_avg < 50:
            parts.append("Low electricity prices: increased pumping to reduce level.")
        elif price_avg > 100:
            parts.append("High electricity prices: minimal pumping while maintaining safety.")
        
        # Level-based message
        if metrics.max_l1_m > 7.0:
            parts.append("Tunnel level approaching upper bound: active pumping to prevent overflow.")
        elif metrics.min_l1_m < 1.0:
            parts.append("Tunnel level low: reduced pumping to maintain minimum level.")
        
        # Strategy message
        guidance_set = set(strategic_guidance[:4])
        if "CHEAP" in guidance_set:
            parts.append("Exploiting cheap price periods for cost savings.")
        if "EXPENSIVE" in guidance_set:
            parts.append("Minimizing pumping during expensive periods.")
        
        explanation = " ".join(parts)
        if not explanation:
            explanation = f"Optimized schedule using {metrics.optimization_mode} mode. Estimated cost: {metrics.total_cost_eur:.2f} EUR."
        
        return explanation

