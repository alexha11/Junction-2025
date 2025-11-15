type Schedule = {
  entries?: {
    pump_id: string;
    target_frequency_hz: number;
    start_time: string;
    end_time: string;
  }[];
  justification?: string;
};

interface Props {
  schedule?: Schedule;
  loading?: boolean;
}

const RecommendationPanel = ({ schedule, loading }: Props) => (
  <div className="glass-card">
    <p className="section-title">AI recommendation</p>
    <h2 className="text-2xl font-semibold text-white">Pump plan</h2>
    {loading ? (
      <div className="mt-6 rounded-2xl border border-white/5 px-4 py-6 text-center text-sm text-slate-400">
        Loading latest schedule...
      </div>
    ) : schedule?.entries ? (
      <ul className="mt-4 space-y-3">
        {schedule.entries.map((entry) => (
          <li
            key={`${entry.pump_id}-${entry.start_time}`}
            className="rounded-2xl border border-white/5 bg-white/5 px-4 py-3 text-sm text-slate-200"
          >
            <div className="flex items-center justify-between">
              <span className="text-base font-semibold text-white">
                {entry.pump_id}
              </span>
              <span className="text-brand-accent">
                {entry.target_frequency_hz.toFixed(1)} Hz
              </span>
            </div>
            <div className="mt-1 text-xs uppercase tracking-wide text-slate-400">
              {new Date(entry.start_time).toLocaleTimeString()} –{" "}
              {new Date(entry.end_time).toLocaleTimeString()}
            </div>
          </li>
        ))}
      </ul>
    ) : (
      <div className="mt-6 rounded-2xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-slate-400">
        No schedule yet. Waiting for latest telemetry.
      </div>
    )}
    {schedule?.justification && !loading && (
      <p className="mt-4 rounded-2xl border border-brand-accent/20 bg-brand-accent/5 px-4 py-3 text-sm text-slate-200">
        {schedule.justification}
      </p>
    )}
  </div>
);

export default RecommendationPanel;
