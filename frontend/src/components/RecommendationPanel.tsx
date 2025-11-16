type Schedule = {
  entries?: {
    pump_id: string;
    target_frequency_hz: number;
    start_time: string;
    end_time: string;
  }[];
  justification?: string;
  strategy?: string;
};

interface Props {
  schedule?: Schedule;
  loading?: boolean;
  onPlayAudio?: () => void;
}

const RecommendationPanel = ({ schedule, loading, onPlayAudio }: Props) => {
  const hasContent = (schedule?.justification && schedule.justification !== "Optimized pump schedule based on current conditions.") || schedule?.strategy;
  
  return (
  <div className="glass-card">
    <div className="flex items-center justify-between">
      <div>
        <p className="section-title">AI recommendation</p>
        <h2 className="text-2xl font-semibold text-white">Pump plan</h2>
      </div>
      {hasContent && !loading && onPlayAudio && (
        <button
          onClick={onPlayAudio}
          className="flex items-center gap-2 rounded-lg bg-brand-accent/20 hover:bg-brand-accent/30 border border-brand-accent/30 px-4 py-2 text-sm font-semibold text-brand-accent transition-colors"
          title="Play audio explanation and strategy"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
            />
          </svg>
          Play Audio
        </button>
      )}
    </div>
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
    {/* Always display explanation and strategy when available, even if no schedule entries */}
    {((schedule?.justification && schedule.justification !== "Optimized pump schedule based on current conditions.") || schedule?.strategy) && !loading && (
      <div className="mt-6 space-y-3">
        {schedule.justification && schedule.justification !== "Optimized pump schedule based on current conditions." && (
          <div className="rounded-2xl border border-brand-accent/20 bg-brand-accent/5 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-accent mb-2">Explanation</p>
            <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{schedule.justification}</p>
          </div>
        )}
        {schedule.strategy && (
          <div className="rounded-2xl border border-blue-400/20 bg-blue-400/5 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-400 mb-2">Strategy</p>
            <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{schedule.strategy}</p>
          </div>
        )}
      </div>
    )}
  </div>
  );
};

export default RecommendationPanel;
