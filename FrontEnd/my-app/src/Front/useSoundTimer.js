import { useEffect, useRef, useState } from "react";

// Countdown starts only after the simulator confirms the timer write.
export function useSoundTimer(onChange, confirmedSound, feedback) {
  const [timer, setTimer] = useState(null);
  const [pending, setPending] = useState(null);
  const [now, setNow] = useState(0);
  const change = useRef(onChange);
  useEffect(() => {
    change.current = onChange;
  }, [onChange]);
  useEffect(() => {
    if (!confirmedSound) {
      setTimer(null);
      setPending(null);
      return;
    }
    if (pending === null) return;
    if (feedback?.status === "error") {
      setPending(null);
      return;
    }
    if (feedback?.status === "saved" && confirmedSound.timer_minutes === pending) {
      const start = Date.now();
      setNow(start);
      setTimer(pending > 0 ? { start, end: start + pending * 60000 } : null);
      setPending(null);
    }
  }, [confirmedSound, feedback?.status, pending]);
  useEffect(() => {
    if (!timer) return;
    const tick = () => {
      const time = Date.now();
      setNow(time);
      if (time >= timer.end) {
        setTimer(null);
        change.current((sound) => ({ ...sound, volume: 0, timer_minutes: 0 }));
      }
    };
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [timer]);
  return {
    confirm(minutes) {
      setPending(null);
      const start = Date.now();
      setNow(start);
      setTimer(minutes > 0 ? { start, end: start + minutes * 60000 } : null);
    },
    configuredMinutes: confirmedSound?.timer_minutes ?? 0,
    running: Boolean(timer),
    starting: pending !== null || Boolean(timer && now - timer.start < 600),
    remaining: timer ? Math.max(0, Math.ceil((timer.end - now) / 1000)) : 0,
    progress: timer ? Math.max(0, Math.min(1, (timer.end - now) / (timer.end - timer.start))) : 0,
    start(minutes) {
      if (!Number.isInteger(minutes) || minutes <= 0 || minutes > 1440) return;
      setPending(minutes);
      change.current((sound) => ({ ...sound, timer_minutes: minutes }));
    },
    cancel() {
      setPending(0);
      change.current((sound) => ({ ...sound, timer_minutes: 0 }));
    },
  };
}
