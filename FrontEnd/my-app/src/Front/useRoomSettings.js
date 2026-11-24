import { initialSettings } from "./roomSettings.js";

// Adapt the shared simulator state to the existing light card.
export function useRoomSettings(simulator) {
  const light = simulator.draft?.light;
  const settings = light
    ? {
        brightness: light.brightness,
        lightOn: light.brightness > 0,
        lightTone: light.color_temperature_k >= 5000 ? "cool" : "warm",
      }
    : initialSettings;
  function setSettings(update) {
    simulator.change("light", (current) => {
      const before = {
        brightness: current.brightness,
        lightOn: current.brightness > 0,
        lightTone: current.color_temperature_k >= 5000 ? "cool" : "warm",
      };
      const next = typeof update === "function" ? update(before) : update;
      return {
        brightness: next.lightOn ? next.brightness : 0,
        color_temperature_k:
          next.lightTone === before.lightTone
            ? current.color_temperature_k
            : next.lightTone === "cool"
              ? 6500
              : 2700,
      };
    });
  }
  return {
    settings,
    setSettings,
    status:
      simulator.load.status === "error"
        ? "load-error"
        : simulator.load.status === "loading"
          ? "loading"
          : (simulator.writes.light?.status ?? "ready"),
    retry: () => (simulator.draft ? simulator.retryDevice("light") : simulator.retryLoad()),
  };
}
