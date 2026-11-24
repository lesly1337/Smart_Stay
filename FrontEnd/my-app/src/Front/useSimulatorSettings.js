import { useEffect, useRef, useState } from "react";
import { createSettingWriter, getDeviceSettings, getTracks, saveDevice } from "./api.js";

export const defaultAlarmTime = "07:30";
const deviceRoutes = {
  light: "light",
  climate: "temperature",
  curtains: "curtains",
  sound: "sound",
  alarm: "alarm",
  dnd: "dnd",
};

export function useSimulatorSettings(blocked = false) {
  const [updatedAt, setUpdatedAt] = useState(null);
  const [draft, setDraft] = useState(null);
  const [confirmed, setConfirmed] = useState(null);
  const [load, setLoad] = useState({ status: "loading" });
  const [writes, setWrites] = useState({});
  const [tracks, setTracks] = useState([]);
  const [catalog, setCatalog] = useState({ status: "loading" });
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const current = useRef(null);
  const writers = useRef({});
  const soundVolume = useRef(20);

  useEffect(() => {
    let active = true;
    const nextWriters = {};
    for (const [device, route] of Object.entries(deviceRoutes)) {
      nextWriters[device] = createSettingWriter(
        async (value) => {
          const actual = await saveDevice(route, value);
          if (active) {
            setConfirmed((previous) => ({ ...previous, [device]: actual }));
            setUpdatedAt(Date.now());
          }
        },
        (status, error) => {
          if (!active) return;
          setWrites((previous) => ({ ...previous, [device]: { status, error: error?.message } }));
        },
      );
    }
    writers.current = nextWriters;

    getDeviceSettings()
      .then((state) => {
        if (!active) return;
        const next = {
          ...state,
          alarm: { ...state.alarm, time: state.alarm.time ?? defaultAlarmTime },
        };
        if (state.sound.volume > 0) soundVolume.current = state.sound.volume;
        current.current = next;
        setDraft(next);
        setConfirmed(state);
        setUpdatedAt(Date.now());
        setLoad({ status: "ready" });
      })
      .catch((error) => {
        if (active) setLoad({ status: "error", error: error.message });
      });

    return () => {
      active = false;
      for (const writer of Object.values(nextWriters)) writer.dispose();
    };
  }, [loadAttempt]);

  useEffect(() => {
    let active = true;
    getTracks()
      .then((items) => {
        if (!active) return;
        setTracks([...items].sort((a, b) => a.track_id.localeCompare(b.track_id)));
        setCatalog({ status: "ready" });
      })
      .catch((error) => {
        if (active) setCatalog({ status: "error", error: error.message });
      });
    return () => {
      active = false;
    };
  }, [catalogAttempt]);

  function change(device, update, force = false) {
    if (!current.current || blocked) return;
    const previous = current.current[device];
    const next = update(previous);
    if (device === "sound" && next.volume > 0) soundVolume.current = next.volume;
    if (!force && Object.keys(next).every((key) => next[key] === previous[key])) return;
    current.current = { ...current.current, [device]: next };
    setDraft(current.current);
    if (device === "alarm" && !previous.enabled && !next.enabled && previous.mode === next.mode)
      return;
    writers.current[device].schedule(next);
  }

  function chooseSound(trackId) {
    change("sound", (sound) => {
      if (sound.volume > 0) soundVolume.current = sound.volume;
      return {
        ...sound,
        track_id: trackId ?? sound.track_id,
        volume:
          (trackId === undefined || trackId === sound.track_id) && sound.volume > 0
            ? 0
            : soundVolume.current,
      };
    });
  }

  function retryDevice(device) {
    if (current.current) writers.current[device]?.schedule(current.current[device]);
  }

  function retryLoad() {
    for (const writer of Object.values(writers.current)) writer.dispose();
    current.current = null;
    setDraft(null);
    setConfirmed(null);
    setWrites({});
    setLoad({ status: "loading" });
    setLoadAttempt((attempt) => attempt + 1);
  }

  function retryCatalog() {
    setCatalog({ status: "loading" });
    setCatalogAttempt((attempt) => attempt + 1);
  }

  async function refresh() {
    const state = await getDeviceSettings();
    const next = {
      ...state,
      alarm: { ...state.alarm, time: state.alarm.time ?? defaultAlarmTime },
    };
    current.current = next;
    setDraft(next);
    setConfirmed(state);
    setLoad({ status: "ready" });
    setUpdatedAt(Date.now());
  }

  useEffect(() => {
    const changed = () => retryLoad();
    window.addEventListener("room-context-changed", changed);
    return () => window.removeEventListener("room-context-changed", changed);
  }, []);

  return {
    updatedAt,
    draft,
    confirmed,
    load,
    writes,
    tracks,
    catalog,
    change,
    chooseSound,
    retryDevice,
    retryLoad,
    retryCatalog,
    refresh,
  };
}
