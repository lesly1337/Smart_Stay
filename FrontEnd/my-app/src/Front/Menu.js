import { useEffect, useLayoutEffect, useRef, useState } from "react";

export function positionLightCard(dialog, anchor) {
  if (!anchor) return;
  const bounds = anchor.getBoundingClientRect();
  const panel = dialog.querySelector(".light-expanded-card");
  const width = panel.offsetWidth || Math.min(210, window.innerWidth - 24);
  panel.style.setProperty(
    "--light-left",
    Math.max(12, Math.min(bounds.left, window.innerWidth - width - 12)) + "px",
  );
  panel.style.setProperty(
    "--light-top",
    Math.max(12, Math.min(bounds.top, window.innerHeight - panel.offsetHeight - 12)) + "px",
  );
  panel.style.setProperty(
    "--card-start-x",
    bounds.left - parseFloat(panel.style.getPropertyValue("--light-left")) + "px",
  );
  panel.style.setProperty(
    "--card-start-y",
    bounds.top - parseFloat(panel.style.getPropertyValue("--light-top")) + "px",
  );
  panel.style.setProperty("--card-scale-x", bounds.width / panel.offsetWidth);
  panel.style.setProperty("--card-scale-y", bounds.height / panel.offsetHeight);
}

export function useBrightnessWheel(value, onChange) {
  const ref = useRef(null);
  const reported = useRef(null);
  const callback = useRef(onChange);
  useLayoutEffect(() => {
    callback.current = onChange;
  }, [onChange]);

  // Runs after the dialog is opened, before the first visible frame.
  useLayoutEffect(() => {
    if (reported.current === value) return;
    const element = ref.current;
    if (!element) return;
    reported.current = value;
    element.scrollTo({ left: (value / 10) * 64, behavior: "instant" });
    paintBrightnessDots(element);
  }, [value]);

  useEffect(() => {
    const element = ref.current;
    const wheel = (event) => {
      event.preventDefault();
      const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
      const index = Math.round(element.scrollLeft / 64);
      const next = Math.max(0, Math.min(10, index + Math.sign(delta)));
      element.scrollTo({
        left: next * 64,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, []);

  return {
    ref,
    onScroll(event) {
      paintBrightnessDots(event.currentTarget);
      const next = Math.max(0, Math.min(100, Math.round(event.currentTarget.scrollLeft / 64) * 10));
      if (next !== reported.current) {
        reported.current = next;
        callback.current(next);
      }
    },
    onKeyDown(event) {
      const delta = { ArrowRight: 10, ArrowUp: 10, ArrowLeft: -10, ArrowDown: -10 }[event.key];
      if (delta === undefined && event.key !== "Home" && event.key !== "End") return;
      event.preventDefault();
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? 100
            : Math.max(0, Math.min(100, value + delta));
      ref.current.scrollTo({
        left: (next / 10) * 64,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
    },
  };
}

export function getBrightnessDotVisual(index, progress) {
  const distance = index - 7 - progress;
  const absolute = Math.abs(distance);
  return {
    x: distance * 14,
    scale: Math.max(0.35, 1 - absolute * 0.12),
    opacity: index < 7 || index > 17 ? 0 : Math.max(0, 1 - absolute / 6),
  };
}

function paintBrightnessDots(wheel) {
  const dots = wheel.nextElementSibling;
  if (!dots?.classList.contains("brightness-wheel-dots")) return;
  const progress = Math.max(0, Math.min(10, wheel.scrollLeft / 64));
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  dots.querySelectorAll("span").forEach((dot, index) => {
    const visual = getBrightnessDotVisual(index, reducedMotion ? Math.round(progress) : progress);
    dot.style.transform = "translateX(" + visual.x + "px) scale(" + visual.scale + ")";
    dot.style.opacity = visual.opacity;
  });
}

export const controlIcons = {
  climate: "M10 14.5V4a2 2 0 0 1 4 0v10.5a4 4 0 1 1-4 0M12 8v9",
  light: "M5 16c0-4 1-9 7-9s7 5 7 9H5ZM12 3v4M9 19a3 3 0 0 0 6 0",
  curtains: "M3 4h18M4 4v16M20 4v16M9 4v12l-3 3M15 4v12l3 3",
  sound: "M3 10v4M7 6v12M11 3v18M15 7v10M19 9v6",
  alarm: "M5 3 2 6M19 3l3 3M6 19l-2 3M18 19l2 3M12 8v5l3 2M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  moon: "M19 16A9 9 0 0 1 8 3a10 10 0 1 0 13 13Z",
  home: "M3 10l9-8 9 8v11h-6v-7H9v7H3Z",
  controls: "M3 6h7M14 6h7M3 12h12M19 12h2M3 18h2M9 18h12M10 3v6M16 9v6M6 15v6",
  back: "m15 4-8 8 8 8",
  arrow: "M12 20V4m-6 6 6-6 6 6",
};

export function useChatSheetDrag(onClose) {
  const panelRef = useRef(null);
  const gesture = useRef(null);
  const suppressClick = useRef(false);
  const [full, setFull] = useState(false);
  const [dragging, setDragging] = useState(false);
  function finish(event, cancelled = false) {
    const current = gesture.current;
    if (!current || current.id !== event.pointerId) return;
    const close = !cancelled && current.moved && !full && current.lastY > current.y + 50;
    if (!cancelled && current.moved && !close)
      setFull(
        current.lastY < current.y - 35 ? true : current.lastY > current.y + 35 ? false : full,
      );
    gesture.current = null;
    const panel = panelRef.current;
    const offset = panel.style.transform || "translateY(0)";
    panelRef.current.style.removeProperty("--chat-height");
    panel.style.removeProperty("transform");
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    if (close) {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        onClose();
        return;
      }
      panel.style.pointerEvents = "none";
      panel
        .animate([{ transform: offset }, { transform: "translateY(100%)" }], {
          duration: 200,
          easing: "ease-in",
          fill: "forwards",
        })
        .finished.then(onClose)
        .catch(onClose);
    }
  }
  return {
    panelRef,
    full,
    dragging,
    handlers: {
      onPointerDown(event) {
        if (!event.isPrimary || event.button !== 0) return;
        suppressClick.current = false;
        gesture.current = {
          id: event.pointerId,
          y: event.clientY,
          lastY: event.clientY,
          height: panelRef.current.offsetHeight,
          moved: false,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
      },
      onPointerMove(event) {
        const current = gesture.current;
        if (!current || current.id !== event.pointerId) return;
        current.lastY = event.clientY;
        if (Math.abs(current.y - event.clientY) < 5 && !current.moved) return;
        current.moved = true;
        suppressClick.current = true;
        setDragging(true);
        if (!full && event.clientY > current.y) {
          panelRef.current.style.removeProperty("--chat-height");
          panelRef.current.style.transform = "translateY(" + (event.clientY - current.y) + "px)";
          return;
        }
        panelRef.current.style.removeProperty("transform");
        const availableHeight = panelRef.current.parentElement.clientHeight;
        const height = Math.min(
          availableHeight,
          Math.max(Math.min(240, availableHeight), current.height + current.y - event.clientY),
        );
        panelRef.current.style.setProperty("--chat-height", height + "px");
      },
      onPointerUp: finish,
      onPointerCancel(event) {
        finish(event, true);
      },
      onLostPointerCapture(event) {
        finish(event, true);
      },
      onClick() {
        if (!suppressClick.current) setFull((value) => !value);
        suppressClick.current = false;
      },
    },
  };
}

export function closeAnimatedCard(dialog, onClose) {
  if (dialog.dataset.closing === "true") return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    onClose();
    return;
  }
  dialog.dataset.closing = "true";
  const panel = dialog.querySelector(".light-expanded-card");
  const style = getComputedStyle(panel);
  const target =
    "translate(" +
    style.getPropertyValue("--card-start-x") +
    "," +
    style.getPropertyValue("--card-start-y") +
    ") scale(" +
    style.getPropertyValue("--card-scale-x") +
    "," +
    style.getPropertyValue("--card-scale-y") +
    ")";
  const animation = panel.animate(
    [
      { transform: style.transform, opacity: 1 },
      { transform: target, opacity: 0 },
    ],
    { duration: 200, easing: "ease-in-out", fill: "forwards" },
  );
  animation.finished.then(onClose).catch(onClose);
}

export const alarmModes = [
  { value: "light", label: "Свет", caption: "Только свет" },
  { value: "sound", label: "Звук", caption: "Только звук" },
  { value: "both", label: "Вместе", caption: "Свет и звук" },
];

export function setAlarmTimePart(time, part, value) {
  const parts = time.split(":");
  parts[part === "hours" ? 0 : 1] = String(value).padStart(2, "0");
  return parts.join(":");
}

export function wrapAlarmValue(value, count) {
  return ((value % count) + count) % count;
}

export function useAlarmWheel(value, count, onChange, rowHeight = 24) {
  const ref = useRef(null);
  const reported = useRef(null);
  const ready = useRef(false);
  const callback = useRef(onChange);
  const settleTimer = useRef(null);
  useLayoutEffect(() => {
    callback.current = onChange;
  }, [onChange]);
  useLayoutEffect(() => {
    if (reported.current === value && ready.current) return;
    ready.current = false;
    const sync = () => {
      ref.current.scrollTo({ top: (count * 2 + value) * rowHeight, behavior: "instant" });
      reported.current = value;
      ready.current = true;
    };
    if (ref.current.closest("dialog")?.open) {
      sync();
      return;
    }
    const frame = requestAnimationFrame(sync);
    return () => cancelAnimationFrame(frame);
  }, [value, count, rowHeight]);

  function recenter() {
    const element = ref.current;
    if (!element || !ready.current) return;
    const position = element.scrollTop / rowHeight;
    const index = Math.round(position);
    const target = count * 2 + wrapAlarmValue(index, count);
    if (index !== target)
      element.scrollTo({ top: (target + position - index) * rowHeight, behavior: "instant" });
  }

  useEffect(() => {
    const element = ref.current;
    const wheel = (event) => {
      event.preventDefault();
      if (!ready.current) return;
      const next = Math.round(element.scrollTop / rowHeight) + Math.sign(event.deltaY);
      element.scrollTo({
        top: next * rowHeight,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
    };
    element.addEventListener("wheel", wheel, { passive: false });
    element.addEventListener("scrollend", recenter);
    return () => {
      clearTimeout(settleTimer.current);
      element.removeEventListener("wheel", wheel);
      element.removeEventListener("scrollend", recenter);
    };
  }, [count, rowHeight]);

  return {
    ref,
    onScroll(event) {
      if (!ready.current) return;
      const element = event.currentTarget;
      const index = Math.round(element.scrollTop / rowHeight);
      const next = wrapAlarmValue(index, count);
      if (next !== reported.current) {
        reported.current = next;
        callback.current(next);
      }
      // Keep spare copies in both directions, including during a long swipe.
      if (index < count || index >= count * 4) recenter();
      clearTimeout(settleTimer.current);
      settleTimer.current = setTimeout(recenter, 180);
    },
    onKeyDown(event) {
      const delta = { ArrowUp: -1, ArrowDown: 1 }[event.key];
      if (delta === undefined && event.key !== "Home" && event.key !== "End") return;
      event.preventDefault();
      const index = Math.round(ref.current.scrollTop / rowHeight);
      const next =
        event.key === "Home" ? count * 2 : event.key === "End" ? count * 3 - 1 : index + delta;
      ref.current.scrollTo({ top: next * rowHeight, behavior: "instant" });
    },
  };
}
