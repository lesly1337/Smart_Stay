const API_BASE = (import.meta.env?.VITE_API_URL || "/api").replace(/\/$/, "");
let sessionPromise = null;
let sessionInfo = null;

function emit(name, detail) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(name, { detail }));
}

function rememberSession(value) {
  if (
    !value ||
    typeof value.run_id !== "string" ||
    typeof value.session_id !== "string" ||
    !Number.isFinite(Date.parse(value.at)) ||
    !Number.isFinite(Date.parse(value.expires_at))
  ) {
    throw new Error("Сервер не вернул корректный сеанс управления.");
  }
  const changed =
    sessionInfo && (sessionInfo.session_id !== value.session_id || sessionInfo.at !== value.at);
  sessionInfo = value;
  if (changed) emit("room-context-changed", value);
  return value;
}

async function fetchJson(path, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(API_BASE + path, { ...options, signal: controller.signal });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const error = new Error(
        typeof body?.detail === "string" ? body.detail : "HTTP " + response.status,
      );
      error.status = response.status;
      if (response.status === 409 || response.status === 410)
        emit("room-session-unavailable", error.message);
      if (response.status === 412) {
        sessionPromise = null;
        sessionInfo = null;
        emit("room-context-changed", null);
      }
      throw error;
    }
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

export function openInteractiveSession(renew = false) {
  if (renew || sessionPromise === null) {
    const pending = fetchJson(
      "/room/session",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ renew }),
      },
      90000,
    ).then(rememberSession);
    sessionPromise = pending;
    pending.catch(() => {
      if (sessionPromise === pending) sessionPromise = null;
    });
  }
  return sessionPromise.then(() => sessionInfo);
}

async function request(path, options = {}, timeoutMs) {
  const session = await openInteractiveSession();
  const value = await fetchJson(
    path,
    {
      ...options,
      headers: { ...options.headers, "X-Room-Session": session.context_id || session.session_id },
    },
    timeoutMs,
  );
  if (value?.session) rememberSession(value.session);
  return value;
}

const post = (path, body = {}, timeoutMs = 90000) =>
  request(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    timeoutMs,
  );

export const getDeviceSettings = () => request("/room/devices", {}, 45000).then(checkDevices);
export const getTracks = () => request("/room/tracks", {}, 45000).then(checkTracks);
export const saveDevice = (device, settings) =>
  request(
    "/room/" + device,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    },
    45000,
  ).then((value) => checkDevice(device, value));
export const getGuests = () =>
  request("/room/guests", {}, 45000).then((value) => {
    if (
      !Array.isArray(value?.guests) ||
      !value.guests.length ||
      value.guests.some((g) => !g.stay_id || !g.label)
    ) {
      throw new Error("Список гостей недоступен.");
    }
    return value;
  });
export const getGuestPlan = () => request("/room/plan", {}, 45000).then(checkPlan);
export const selectGuest = (stayId) => post("/room/guest", { stay_id: stayId }).then(checkPlan);
export const prepareGuestPlan = () => post("/room/plan/prepare", {}, 180000).then(checkPlan);
export const applyGuestPlan = () => post("/room/plan/apply").then(checkPlan);
export const setRoomTime = (at) => post("/room/time", { at }).then(checkPlan);
export const sendGuestCommand = (text, commandId) =>
  post("/room/command", { text, command_id: commandId }, 180000).then((value) => {
    if (
      !Array.isArray(value?.replies) ||
      !value.replies.length ||
      value.replies.some(
        (r) => !["done", "refused"].includes(r.response_class) || typeof r.text !== "string",
      )
    ) {
      throw new Error("Помощник не вернул подтверждённый результат.");
    }
    return value;
  });

function checkPlan(value) {
  if (
    !value?.stay?.record_id ||
    !Array.isArray(value.periods) ||
    value.periods.length !== 3 ||
    value.periods.some(
      (p) => !p.id || !p.title || !Array.isArray(p.times) || !Array.isArray(p.details) || !p.at,
    ) ||
    new Set(value.periods.map((p) => p.id)).size !== 3 ||
    !["evening", "night", "morning"].every((id) => value.periods.some((p) => p.id === id)) ||
    !value.preferences ||
    !["draft", "applied"].includes(value.status) ||
    !Array.isArray(value.steps) ||
    !Array.isArray(value.assumptions)
  )
    throw new Error("Сервер не вернул план отдыха.");
  return value;
}

// Serial writes: an older request can never finish after a newer one.
export function createSettingWriter(save, notify, delay = 350) {
  let pending = null,
    busy = false,
    timer = null,
    disposed = false;
  async function flush() {
    if (busy || pending === null || disposed) return;
    const value = pending;
    pending = null;
    busy = true;
    try {
      await save(value);
      if (!disposed && pending === null) notify("saved");
    } catch (error) {
      if (!disposed && pending === null) notify("error", error);
    } finally {
      busy = false;
      if (!disposed && pending !== null) {
        clearTimeout(timer);
        timer = setTimeout(flush, delay);
      }
    }
  }
  return {
    schedule(value) {
      if (disposed) return;
      pending = value;
      notify("saving");
      clearTimeout(timer);
      timer = setTimeout(flush, delay);
    },
    dispose() {
      disposed = true;
      clearTimeout(timer);
    },
  };
}

function checkDevice(device, value) {
  const numberIn = (number, min, max) =>
    typeof number === "number" && Number.isFinite(number) && number >= min && number <= max;
  const valid =
    value &&
    {
      light: () =>
        Number.isInteger(value.brightness) &&
        numberIn(value.brightness, 0, 100) &&
        Number.isInteger(value.color_temperature_k) &&
        numberIn(value.color_temperature_k, 2200, 6500),
      temperature: () => numberIn(value.temperature, 16, 26),
      curtains: () => Number.isInteger(value.position) && numberIn(value.position, 0, 100),
      sound: () =>
        typeof value.track_id === "string" &&
        value.track_id.length > 0 &&
        Number.isInteger(value.volume) &&
        numberIn(value.volume, 0, 100) &&
        (value.timer_minutes === undefined ||
          (Number.isInteger(value.timer_minutes) && numberIn(value.timer_minutes, 0, 1440))),
      alarm: () =>
        typeof value.enabled === "boolean" &&
        ["light", "sound", "both"].includes(value.mode) &&
        ((!value.enabled && value.time === null) ||
          (typeof value.time === "string" && /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(value.time))),
      dnd: () => typeof value.enabled === "boolean",
    }[device]?.();
  if (!valid) throw new Error("Некорректные настройки устройства от сервера.");
  return value;
}
function checkDevices(state) {
  if (!state || typeof state !== "object") throw new Error("Сервер не вернул настройки номера.");
  for (const [key, route] of Object.entries({
    light: "light",
    climate: "temperature",
    curtains: "curtains",
    sound: "sound",
    alarm: "alarm",
    dnd: "dnd",
  }))
    checkDevice(route, state[key]);
  return state;
}
function checkTracks(tracks) {
  if (
    !Array.isArray(tracks) ||
    !tracks.length ||
    tracks.some(
      (track) =>
        !track ||
        typeof track.track_id !== "string" ||
        !track.track_id ||
        typeof track.title !== "string",
    ) ||
    new Set(tracks.map((track) => track.track_id)).size !== tracks.length
  ) {
    throw new Error("Сервер не вернул корректный каталог звуков.");
  }
  return tracks;
}
