import { useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./GuestSelect.css";

export default function GuestSelect({ guests, value, disabled, onChange, formatDates }) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState(null);
  const trigger = useRef(null);
  const panel = useRef(null);
  const id = useId();
  const selected = guests.find((guest) => guest.stay_id === value);
  const visible = open && !disabled;
  const close = (focus = false) => {
    setOpen(false);
    if (focus) trigger.current?.focus();
  };
  useLayoutEffect(() => {
    if (!visible) return;
    const place = () => {
      const rect = trigger.current.getBoundingClientRect();
      const viewport = window.visualViewport;
      const leftEdge = (viewport?.offsetLeft || 0) + 12;
      const topEdge = (viewport?.offsetTop || 0) + 12;
      const rightEdge = leftEdge + (viewport?.width || innerWidth) - 24;
      const bottomEdge = topEdge + (viewport?.height || innerHeight) - 24;
      const below = bottomEdge - rect.bottom - 8;
      const above = rect.top - topEdge - 8;
      const up = below < 180 && above > below;
      const width = Math.min(rect.width, rightEdge - leftEdge);
      const height = Math.min(320, Math.max(0, up ? above : below));
      setPlacement({
        left: Math.max(leftEdge, Math.min(rect.left, rightEdge - width)),
        width,
        maxHeight: height,
        top: up
          ? Math.max(topEdge, rect.top - 8 - Math.min(height, guests.length * 64 + 12))
          : rect.bottom + 8,
      });
    };
    const outside = (event) => {
      if (!panel.current?.contains(event.target) && !trigger.current?.contains(event.target))
        setOpen(false);
    };
    place();
    const frame = requestAnimationFrame(() =>
      panel.current?.querySelector('[aria-selected="true"]')?.focus(),
    );
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    window.visualViewport?.addEventListener("resize", place);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      window.visualViewport?.removeEventListener("resize", place);
    };
  }, [visible, guests.length]);
  function keys(event) {
    const items = [...panel.current.querySelectorAll('[role="option"]')];
    const index = items.indexOf(document.activeElement);
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    }
    if (event.key === "Tab") close();
    const next =
      event.key === "ArrowDown"
        ? (index + 1) % items.length
        : event.key === "ArrowUp"
          ? (index - 1 + items.length) % items.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : null;
    if (next !== null) {
      event.preventDefault();
      items[next]?.focus();
    }
  }
  return (
    <div className="guest-select-label">
      <span id={`${id}-label`}>Гость</span>
      <button
        ref={trigger}
        type="button"
        className="guest-select-trigger"
        disabled={disabled}
        aria-labelledby={`${id}-label ${id}-value`}
        aria-haspopup="listbox"
        aria-expanded={visible}
        aria-controls={visible ? id : undefined}
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span id={`${id}-value`}>
          {selected ? `${selected.label} · ${formatDates(selected)}` : "Выберите гостя"}
        </span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="m6 9 6 6 6-6"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {visible &&
        createPortal(
          <div
            ref={panel}
            id={id}
            role="listbox"
            aria-labelledby={`${id}-label`}
            className="guest-select-menu"
            style={placement || { visibility: "hidden" }}
            onKeyDown={keys}
          >
            {guests.map((guest) => (
              <button
                key={guest.stay_id}
                type="button"
                role="option"
                aria-selected={guest.stay_id === value}
                tabIndex={-1}
                onClick={() => {
                  close(true);
                  onChange(guest.stay_id);
                }}
              >
                <span>
                  <strong>{guest.label}</strong>
                  <small>{formatDates(guest)}</small>
                </span>
                {guest.stay_id === value && (
                  <span className="guest-select-check" aria-hidden="true">
                    ✓
                  </span>
                )}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
