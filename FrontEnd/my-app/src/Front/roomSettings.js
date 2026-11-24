export const initialSettings = {
  brightness: 0,
  lightOn: false,
  lightTone: "warm",
};

export function updateRoomSetting(current, name, value) {
  if (name === "brightness") {
    const brightness = Math.max(0, Math.min(100, Math.round(value / 10) * 10));
    return { ...current, brightness, lightOn: brightness > 0 };
  }
  if (name === "lightOn") {
    return { ...current, lightOn: value, brightness: value ? current.brightness || 20 : 0 };
  }
  return { ...current, [name]: value };
}
