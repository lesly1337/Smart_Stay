import { useLayoutEffect, useRef } from "react";
import { useDismissSheet } from "./useDismissSheet.js";
import moonIcon from "./images/moon.svg";
import sunriseIcon from "./images/sunrise.svg";

function preferenceDetails(plan, tracks) {
  const fields = plan.preferences;
  const temperature = {
    cool: "Прохладный сон: 17–18 °C",
    normal: "Умеренная температура: 19–20 °C",
    warm: "Тёплый сон: 21–22 °C",
  };
  const favorites = fields.favorite_track_ids?.value;
  const sound =
    favorites === null
      ? "Любимые звуки пока не уточнены"
      : !favorites?.length
        ? "Предпочитает тишину"
        : "Любимые звуки: " +
          favorites
            .map((id) => tracks.find((t) => t.track_id === id)?.title || "Выбранный трек")
            .join(", ");
  return [
    temperature[fields.temperature?.value] || "Температура сна пока не уточнена",
    sound,
    fields.gentle_alarm?.value === true
      ? "Мягкое пробуждение светом"
      : fields.gentle_alarm?.value === false
        ? "Допускает звуковой будильник"
        : "Предпочтение будильника пока не уточнено",
  ];
}

export default function PlanExplanation({ plan, tracks, onApply, busy, onClose, error }) {
  const ref = useRef(null);
  const sheet = useDismissSheet(onClose);
  useLayoutEffect(() => {
    const dialog = ref.current;
    const previousFocus = document.activeElement;
    const overflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      previousFocus?.focus();
    };
  }, []);
  const night = plan.periods.find((p) => p.id === "night");
  const morning = plan.periods.find((p) => p.id === "morning");
  return (
    <dialog
      ref={ref}
      id="settings-explanation"
      className="plan-dialog"
      aria-labelledby="plan-explanation-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section ref={sheet.panelRef} className="plan-sheet">
        <button
          type="button"
          className="sound-sheet-handle"
          aria-label="Закрыть пояснение плана"
          {...sheet.handlers}
        >
          <span />
        </button>
        <h2 id="plan-explanation-title">Почему такие настройки?</h2>
        {error && (
          <p className="plan-error" role="alert">
            {error}
          </p>
        )}
        <div className="plan-explanation-content">
          <h3>
            {plan.personalization === "history" ? "Анкета и история гостя" : "План по анкете гостя"}
          </h3>
          <ul>
            {preferenceDetails(plan, tracks).map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
          <div className="plan-event">
            <span className="plan-event-icon" aria-hidden="true">
              <img src={moonIcon} alt="" />
            </span>
            <div>
              <h4>Сон в {night.times[0]}</h4>
              {night.details.map((detail) => (
                <p key={detail}>{detail}</p>
              ))}
            </div>
          </div>
          <div className="plan-event">
            <span className="plan-event-icon" aria-hidden="true">
              <img src={sunriseIcon} alt="" />
            </span>
            <div>
              <h4>Подъём в {morning.times.at(-1)}</h4>
              {morning.details.map((detail) => (
                <p key={detail}>{detail}</p>
              ))}
            </div>
          </div>
          <p>Время указано в часовом поясе отеля: {plan.stay.hotel_timezone}.</p>
          {Math.abs(plan.timezone_difference_hours) >= 3 && (
            <p>
              Разница с домашним поясом: {plan.timezone_difference_hours} ч. Отбой скорректирован на
              один час в сторону местного времени.
            </p>
          )}
          {plan.assumptions.length > 0 && (
            <>
              <h3>Что ещё нужно уточнить</h3>
              <ul>
                {plan.assumptions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          <p className="plan-automation-note">
            {plan.status === "applied"
              ? "Сценарий загружен и подтверждён симулятором. Ручные изменения могут отличаться от плана."
              : "Сценарий подготовлен. Чтобы загрузить его в симулятор, нажмите «Применить план»."}
          </p>
        </div>
        <button type="button" className="plan-configure" disabled={busy} onClick={onApply}>
          {busy ? "Подождите…" : "Применить план"}
        </button>
      </section>
    </dialog>
  );
}
