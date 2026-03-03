from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev
from typing import Dict, Iterable, List

try:
    from .data_loader import LevelVolumeCurve
    from .models import PumpSpec, PumpState, RunSummary, ScheduleDecision, TimeStepData
except ImportError:  # pragma: no cover - allows running as script
    from data_loader import LevelVolumeCurve
    from models import PumpSpec, PumpState, RunSummary, ScheduleDecision, TimeStepData


DT_SECONDS = 900
DT_HOURS = DT_SECONDS / 3600.0
L1_MIN = 0.0
L1_MAX = 8.0
DAILY_FLUSH_TARGET = 0.5


DEFAULT_PUMPS: List[PumpSpec] = [
    PumpSpec("1.1", "small", flow_m3_s=0.42, power_kw=190.0, efficiency=0.72),
    PumpSpec("2.1", "small", flow_m3_s=0.42, power_kw=190.0, efficiency=0.72),
    PumpSpec("1.2", "big", flow_m3_s=0.84, power_kw=390.0, efficiency=0.80),
    PumpSpec("1.3", "big", flow_m3_s=0.84, power_kw=390.0, efficiency=0.80),
    PumpSpec("1.4", "big", flow_m3_s=0.84, power_kw=390.0, efficiency=0.80),
    PumpSpec("2.2", "big", flow_m3_s=0.84, power_kw=390.0, efficiency=0.80),
    PumpSpec("2.3", "big", flow_m3_s=0.84, power_kw=390.0, efficiency=0.80),
    PumpSpec("2.4", "big", flow_m3_s=0.84, power_kw=390.0, efficiency=0.80),
]


@dataclass
class SchedulerConfig:
    level_target_m: float = 2.5
    flush_inflow_threshold_m3_s: float = 1.0
    rain_inflow_threshold_m3_s: float = 2.0
    cheap_price_quantile: float = 0.30
    expensive_price_quantile: float = 0.80
    max_daily_runtime_spread_hours: float = 2.0


class PumpScheduler:
    def __init__(
        self,
        pumps: Iterable[PumpSpec] = DEFAULT_PUMPS,
        config: SchedulerConfig | None = None,
    ) -> None:
        self.pumps = list(pumps)
        self.config = config or SchedulerConfig()
        self._pump_map = {p.pump_id: p for p in self.pumps}

    def run(self, series: List[TimeStepData], curve: LevelVolumeCurve) -> tuple[List[ScheduleDecision], RunSummary]:
        if not series:
            raise ValueError("Cannot schedule empty time series")

        states: Dict[str, PumpState] = {p.pump_id: PumpState() for p in self.pumps}
        daily_flush_done: Dict[date, bool] = defaultdict(bool)
        per_pump_runtime_hours: Dict[str, float] = {p.pump_id: 0.0 for p in self.pumps}
        daily_runtime_hours: Dict[date, Dict[str, float]] = defaultdict(
            lambda: {p.pump_id: 0.0 for p in self.pumps}
        )

        price_values = [s.price_c_per_kwh for s in series]
        sorted_prices = sorted(price_values)
        cheap_cut = sorted_prices[max(0, int(len(sorted_prices) * self.config.cheap_price_quantile) - 1)]
        expensive_cut = sorted_prices[max(0, int(len(sorted_prices) * self.config.expensive_price_quantile) - 1)]

        level = series[0].level_m
        volume = series[0].volume_m3

        decisions: List[ScheduleDecision] = []
        l1_min_violations = 0
        l1_max_violations = 0

        for i, step in enumerate(series):
            lookahead = series[i : min(i + 8, len(series))]
            avg_inflow = mean(s.inflow_m3_s for s in lookahead)

            flush_active = self._should_flush(step, daily_flush_done[step.timestamp.date()])
            target_outflow = self._compute_target_outflow(
                level=level,
                inflow_m3_s=step.inflow_m3_s,
                avg_inflow_m3_s=avg_inflow,
                price_c_per_kwh=step.price_c_per_kwh,
                cheap_cut=cheap_cut,
                expensive_cut=expensive_cut,
                flush_active=flush_active,
            )

            day = step.timestamp.date()
            day_runtimes = daily_runtime_hours[day]
            chosen = self._choose_pumps(target_outflow, states, level, day_runtimes)
            if not chosen:
                chosen = [self.pumps[0].pump_id]

            outflow = sum(self._pump_flow_at_level(self._pump_map[p], level) for p in chosen)
            power = sum(self._pump_power_at_level(self._pump_map[p], level) for p in chosen)

            level_before = level
            volume = volume + (step.inflow_m3_s - outflow) * DT_SECONDS
            min_volume = curve.level_to_volume(L1_MIN)
            max_volume = curve.level_to_volume(L1_MAX)
            volume = max(min_volume, min(volume, max_volume))
            level = max(L1_MIN, min(curve.volume_to_level(volume), L1_MAX))

            if level < L1_MIN:
                l1_min_violations += 1
            if level > L1_MAX:
                l1_max_violations += 1

            energy_kwh = power * DT_HOURS
            cost_eur = energy_kwh * (step.price_c_per_kwh / 100.0)

            if level <= DAILY_FLUSH_TARGET:
                daily_flush_done[step.timestamp.date()] = True

            for pump_id in chosen:
                per_pump_runtime_hours[pump_id] += DT_HOURS
                daily_runtime_hours[day][pump_id] += DT_HOURS

            self._advance_states(states, chosen)

            decisions.append(
                ScheduleDecision(
                    timestamp=step.timestamp,
                    level_before_m=level_before,
                    level_after_m=level,
                    inflow_m3_s=step.inflow_m3_s,
                    outflow_m3_s=outflow,
                    price_c_per_kwh=step.price_c_per_kwh,
                    pumps_on=sorted(chosen),
                    total_power_kw=power,
                    energy_kwh=energy_kwh,
                    cost_eur=cost_eur,
                    flush_active=flush_active,
                )
            )

        summary = self._summarize(
            decisions,
            l1_min_violations,
            l1_max_violations,
            per_pump_runtime_hours,
            daily_runtime_hours,
        )
        return decisions, summary

    def _should_flush(self, step: TimeStepData, already_flushed: bool) -> bool:
        if already_flushed:
            return False
        if step.inflow_m3_s >= self.config.rain_inflow_threshold_m3_s:
            return False
        return step.inflow_m3_s <= self.config.flush_inflow_threshold_m3_s

    def _compute_target_outflow(
        self,
        level: float,
        inflow_m3_s: float,
        avg_inflow_m3_s: float,
        price_c_per_kwh: float,
        cheap_cut: float,
        expensive_cut: float,
        flush_active: bool,
    ) -> float:
        # Keep outflow close to inflow for smooth F2, add feedback to hold level near target.
        level_err = level - self.config.level_target_m
        feedback = 0.20 * level_err
        target = avg_inflow_m3_s + feedback

        # Price-aware buffering: pump more in cheap periods, less in expensive periods.
        if price_c_per_kwh <= cheap_cut:
            target += 0.25
        elif price_c_per_kwh >= expensive_cut:
            target -= 0.20

        if flush_active:
            target = max(target, inflow_m3_s + 1.0)

        # Safety actions near hard bounds.
        if level >= 7.5:
            target = max(target, inflow_m3_s + 1.2)
        if level <= 0.7:
            target = min(target, max(0.2, inflow_m3_s - 0.4))

        return max(0.2, target)

    def _choose_pumps(
        self,
        target_outflow: float,
        states: Dict[str, PumpState],
        level: float,
        day_runtime_hours: Dict[str, float],
    ) -> List[str]:
        forced_on = []
        forced_off = []
        for pump in self.pumps:
            st = states[pump.pump_id]
            if st.is_on and st.steps_in_state < pump.min_on_steps:
                forced_on.append(pump.pump_id)
            if (not st.is_on) and st.steps_in_state < pump.min_off_steps:
                forced_off.append(pump.pump_id)

        available = [p for p in self.pumps if p.pump_id not in forced_off]

        # Balance daily runtime while still preferring efficient pumps.
        min_runtime = min(day_runtime_hours.values()) if day_runtime_hours else 0.0
        allowed = [
            p
            for p in available
            if (
                day_runtime_hours.get(p.pump_id, 0.0)
                <= min_runtime + self.config.max_daily_runtime_spread_hours
            )
            or p.pump_id in forced_on
        ]
        if not allowed:
            allowed = available

        available_sorted = sorted(
            allowed,
            key=lambda p: (
                day_runtime_hours.get(p.pump_id, 0.0),
                -p.efficiency,
                -p.flow_m3_s,
            ),
        )

        chosen = set(forced_on)
        flow = sum(self._pump_flow_at_level(self._pump_map[p], level) for p in chosen)
        if flow >= target_outflow:
            return list(chosen)

        for pump in available_sorted:
            if pump.pump_id in chosen:
                continue
            chosen.add(pump.pump_id)
            flow += self._pump_flow_at_level(pump, level)
            if flow >= target_outflow:
                break

        if not chosen:
            chosen.add(available_sorted[0].pump_id if available_sorted else self.pumps[0].pump_id)

        return list(chosen)

    def _pump_flow_at_level(self, pump: PumpSpec, level_m: float) -> float:
        # Simplified curve: lower suction level reduces delivered flow.
        scale = 0.55 + 0.06 * max(0.0, min(level_m, 8.0))
        scale = max(0.45, min(scale, 1.0))
        return pump.flow_m3_s * scale

    def _pump_power_at_level(self, pump: PumpSpec, level_m: float) -> float:
        # Slightly lower energy at higher level due lower effective lift in this simplified model.
        scale = 1.10 - 0.03 * max(0.0, min(level_m, 8.0))
        scale = max(0.80, min(scale, 1.15))
        return pump.power_kw * scale

    def _advance_states(self, states: Dict[str, PumpState], pumps_on: List[str]) -> None:
        on_set = set(pumps_on)
        for pump in self.pumps:
            st = states[pump.pump_id]
            now_on = pump.pump_id in on_set
            if now_on == st.is_on:
                st.steps_in_state += 1
            else:
                st.is_on = now_on
                st.steps_in_state = 1

    def _summarize(
        self,
        decisions: List[ScheduleDecision],
        vmin: int,
        vmax: int,
        per_pump_runtime_hours: Dict[str, float],
        daily_runtime_hours: Dict[date, Dict[str, float]],
    ) -> RunSummary:
        levels = [d.level_after_m for d in decisions]
        outflows = [d.outflow_m3_s for d in decisions]
        energies = [d.energy_kwh for d in decisions]
        costs = [d.cost_eur for d in decisions]
        pumped_volume_m3 = sum(d.outflow_m3_s * DT_SECONDS for d in decisions)
        flush_days = len(
            {
                d.timestamp.date()
                for d in decisions
                if d.level_after_m <= DAILY_FLUSH_TARGET
            }
        )
        daily_spreads = []
        for runtimes in daily_runtime_hours.values():
            values = list(runtimes.values())
            daily_spreads.append(max(values) - min(values))
        max_daily_spread = max(daily_spreads) if daily_spreads else 0.0
        balance_violations = len(
            [s for s in daily_spreads if s > self.config.max_daily_runtime_spread_hours]
        )

        return RunSummary(
            steps=len(decisions),
            min_level_m=min(levels),
            max_level_m=max(levels),
            avg_outflow_m3_s=mean(outflows),
            outflow_std_m3_s=pstdev(outflows) if len(outflows) > 1 else 0.0,
            total_energy_kwh=sum(energies),
            total_cost_eur=sum(costs),
            specific_energy_kwh_per_m3=(sum(energies) / pumped_volume_m3) if pumped_volume_m3 > 0 else 0.0,
            violation_l1_min_steps=vmin,
            violation_l1_max_steps=vmax,
            daily_flush_hits=flush_days,
            per_pump_runtime_hours=per_pump_runtime_hours,
            max_daily_runtime_spread_hours=max_daily_spread,
            daily_runtime_balance_violations=balance_violations,
        )
