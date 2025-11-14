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
    <div className="card">
      <h2>Manual Override</h2>
      <form onSubmit={handleSubmit}>
        <textarea
          placeholder="Describe why the AI plan is overridden"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={4}
          style={{ width: "100%", borderRadius: "0.5rem", padding: "0.5rem" }}
        />
        <button
          type="submit"
          style={{ marginTop: "0.75rem", padding: "0.5rem 1rem", borderRadius: "0.5rem" }}
        >
          Submit
        </button>
      </form>
      {submitted && <div style={{ marginTop: "0.5rem" }}>Override logged. Thank you.</div>}
      {schedule?.generated_at && (
        <p style={{ opacity: 0.6 }}>
          Last recommendation:{" "}
          {new Date(schedule.generated_at).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
};

export default OverridePanel;
