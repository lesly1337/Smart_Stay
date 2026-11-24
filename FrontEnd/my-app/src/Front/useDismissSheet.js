import { useRef } from "react";

export function useDismissSheet(onClose) {
  const panelRef = useRef(null);
  const gesture = useRef(null);
  const suppressClick = useRef(false);
  const closing = useRef(false);

  function finish(event, cancelled = false) {
    const drag = gesture.current;
    if (!drag || drag.id !== event.pointerId) return;
    gesture.current = null;
    const panel = panelRef.current;
    const dismiss = !cancelled && drag.offset >= 50;
    closing.current = dismiss;
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    const from = panel.style.transform || "translateY(0)";
    panel.style.removeProperty("transform");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      if (dismiss) onClose();
      return;
    }
    const animation = panel.animate(
      [{ transform: from }, { transform: dismiss ? "translateY(100%)" : "translateY(0)" }],
      { duration: 220, easing: "ease-out", fill: "forwards" },
    );
    animation.finished
      .then(() => {
        if (dismiss) onClose();
        else animation.cancel();
      })
      .catch(() => {});
  }

  return {
    panelRef,
    handlers: {
      onPointerDown(event) {
        if (!event.isPrimary || event.button !== 0 || closing.current) return;
        panelRef.current.getAnimations().forEach((animation) => animation.cancel());
        suppressClick.current = false;
        gesture.current = { id: event.pointerId, y: event.clientY, offset: 0 };
        event.currentTarget.setPointerCapture(event.pointerId);
      },
      onPointerMove(event) {
        const drag = gesture.current;
        if (!drag || drag.id !== event.pointerId) return;
        const delta = event.clientY - drag.y;
        if (Math.abs(delta) > 5) suppressClick.current = true;
        drag.offset = Math.max(0, delta);
        panelRef.current.style.transform = `translateY(${drag.offset}px)`;
      },
      onPointerUp: finish,
      onPointerCancel(event) {
        finish(event, true);
      },
      onLostPointerCapture(event) {
        finish(event, true);
      },
      onClick() {
        if (!suppressClick.current && !closing.current) onClose();
        suppressClick.current = false;
      },
    },
  };
}
