export const BOOSTER_PUMP_IDS = ["P2,1", "P2.1", "P1,1", "P1.1"] as const;

export const isBoosterPump = (id?: string) =>
  typeof id === "string" &&
  BOOSTER_PUMP_IDS.some(
    (canonical) => canonical.toLowerCase() === id.toLowerCase()
  );
