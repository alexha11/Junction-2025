type Schedule = {
  entries?: {
    pump_id: string;
    target_frequency_hz: number;
    start_time: string;
    end_time: string;
  }[];
  justification?: string;
};

const RecommendationPanel = ({ schedule }: { schedule?: Schedule }) => (
  <div className="card">
    <h2>AI Recommendation</h2>
    {schedule?.entries ? (
      <ul>
        {schedule.entries.map((entry) => (
          <li key={`${entry.pump_id}-${entry.start_time}`}>
            {entry.pump_id}: {entry.target_frequency_hz.toFixed(1)} Hz |{" "}
            {new Date(entry.start_time).toLocaleTimeString()} -{" "}
            {new Date(entry.end_time).toLocaleTimeString()}
          </li>
        ))}
      </ul>
    ) : (
      <div>No schedule yet.</div>
    )}
    <p style={{ opacity: 0.7 }}>{schedule?.justification}</p>
  </div>
);

export default RecommendationPanel;
