import { useEffect, useRef, useState } from "react";
import {
  applyGuestPlan,
  getGuestPlan,
  getGuests,
  prepareGuestPlan,
  selectGuest,
  setRoomTime,
} from "./api.js";

export function useGuestPlan() {
  const [plan, setPlan] = useState(null);
  const [guests, setGuests] = useState([]);
  const [load, setLoad] = useState({ status: "loading" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const running = useRef(false);

  useEffect(() => {
    let active = true;
    Promise.all([getGuests(), getGuestPlan()])
      .then(([list, value]) => {
        if (!active) return;
        setGuests(list.guests);
        setPlan(value);
        setLoad({ status: "ready" });
      })
      .catch((failure) => {
        if (active) setLoad({ status: "error", error: failure.message });
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  useEffect(() => {
    const changed = () => setAttempt((value) => value + 1);
    window.addEventListener("room-context-changed", changed);
    return () => window.removeEventListener("room-context-changed", changed);
  }, []);

  async function run(action) {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setError("");
    try {
      const value = await action();
      setPlan(value);
      return value;
    } catch (failure) {
      setError(failure.message);
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  return {
    plan,
    guests,
    load,
    busy,
    error,
    retry: () => {
      setLoad({ status: "loading" });
      setAttempt((value) => value + 1);
    },
    select: (id) => run(() => selectGuest(id)),
    personalize: () => run(prepareGuestPlan),
    apply: () => run(applyGuestPlan),
    clock: (at) => run(() => setRoomTime(at)),
  };
}
