import { useState } from "react";

const OverridePanel = ({ schedule }: { schedule?: any }) => {
  const [reason, setReason] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!reason) return;
    // TODO: POST to backend override endpoint
    setSubmitted(true);
  };

  return (
    <div className="glass-card">
      <p className="section-title">Operations guardrail</p>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-2xl font-semibold">Manual override</h2>
        {schedule?.generated_at && (
          <span className="text-xs text-slate-400">
            last AI plan ·{" "}
            {new Date(schedule.generated_at).toLocaleTimeString()}
          </span>
        )}
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <textarea
          placeholder="Describe why the AI plan is adjusted (context, risk, stakeholders)."
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={4}
          className="w-full resize-none rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-base text-white placeholder:text-slate-500 focus:border-brand-accent focus:outline-none focus:ring-2 focus:ring-brand-accent/40"
        />
        <button
          type="submit"
          className="inline-flex w-full items-center justify-center rounded-2xl bg-gradient-to-r from-brand-hsy to-brand-valmet px-4 py-3 text-sm font-semibold uppercase tracking-wide text-white hover:from-brand-hsy/80 hover:to-brand-valmet/80 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!reason}
        >
          Log override
        </button>
      </form>
      {submitted && (
        <div className="mt-4 rounded-2xl border border-brand-valmet/40 bg-brand-valmet/10 px-4 py-2 text-sm text-brand-valmet">
          Override logged. Thank you for keeping the loop human-aware.
        </div>
      )}
    </div>
  );
};

export default OverridePanel;
