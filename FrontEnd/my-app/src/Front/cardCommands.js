// Settings exposed by cards. Returns null for unsupported/ambiguous input.
export function parseCardCommand(text) {
  const s = text
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[«»".!?]/g, "")
    .trim();
  const on = /включ|активир|запусти/.test(s);
  const off = /выключ|отключ|деактивир/.test(s);
  if (/не беспокоить|небеспокоить|\bdnd\b/.test(s)) {
    const rest = s.replace(/не беспокоить|небеспокоить|\bdnd\b/g, "режим");
    if (/(^|\s)не\s/.test(rest) || on === off || /будильник|свет|штор|громкость/.test(rest))
      return null;
    return { device: "dnd", enabled: on };
  }
  if (/(^|\s)(не|нельзя)\s/.test(s)) return null;
  if (/будильник/.test(s)) {
    const mode = /вместе|свет(?:ом)? и звук|звук(?:ом)? и свет/.test(s)
      ? "both"
      : /свет/.test(s)
        ? "light"
        : /звук/.test(s)
          ? "sound"
          : undefined;
    const match = s.match(/(?:на|в)\s+(\d{1,2})(?:[:\- ](\d{2}))?(?:\s*(утра|вечера|дня|ночи))?/);
    if (on && off) return null;
    if (/\d/.test(s) && !match) return null;
    let time;
    if (match) {
      let hour = Number(match[1]);
      const minute = Number(match[2] || 0);
      if (hour > 23 || minute > 59) return null;
      if (match[3] && (hour < 1 || hour > 12)) return null;
      if (/вечера|дня/.test(match[3] || "")) hour = (hour % 12) + 12;
      if (/утра|ночи/.test(match[3] || "")) hour %= 12;
      time = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
    }
    if (mode || on || off)
      return {
        device: "alarm",
        ...(mode ? { mode } : {}),
        ...(time ? { time, enabled: true } : {}),
        ...(off ? { enabled: false } : on ? { enabled: true } : {}),
      };
    return null;
  }
  if (/таймер/.test(s)) return null; // Handled by the duration parser.
  const numeric = s.match(/-?\d+(?:[.,]\d+)?/g) || [];
  const value = numeric.length === 1 ? Number(numeric[0].replace(",", ".")) : null;
  const light = /свет|яркост|освещ|ламп/.test(s);
  const volume = /громкост|громче|тише|потише|погромче/.test(s);
  const climate = /температур|градус|климат/.test(s) && !/цветов/.test(s);
  if ([light, volume, climate].filter(Boolean).length > 1) return null;
  if (light) {
    if (/тепл/.test(s) !== /холодн/.test(s) && value === null && !numeric.length)
      return { device: "lightTone", tone: /тепл/.test(s) ? "warm" : "cool" };
    if (numeric.length)
      return Number.isInteger(value) && value >= 0 && value <= 100
        ? { device: "brightness", value }
        : null;
    if (/ярче|поярче/.test(s) !== /тусклее|приглуш|потемнее/.test(s))
      return { device: "brightness", delta: /ярче|поярче/.test(s) ? 10 : -10 };
  }
  if (volume) {
    if (numeric.length)
      return Number.isInteger(value) && value >= 0 && value <= 100
        ? { device: "volume", value }
        : null;
    if (/громче|погромче/.test(s) !== /тише|потише/.test(s))
      return { device: "volume", delta: /тише|потише/.test(s) ? -10 : 10 };
  }
  if (climate && numeric.length)
    return value !== null && value >= 16 && value <= 26 ? { device: "climate", value } : null;
  return null;
}
