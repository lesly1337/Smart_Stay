import { useState } from "react";
import { useAlarmWheel } from "./Menu.js";

function TimerColumn({ value, count, label, onChange }) {
  const wheel = useAlarmWheel(value, count, onChange, 38);
  return (
    <div
      className="alarm-wheel"
      role="spinbutton"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={count - 1}
      aria-valuenow={value}
      {...wheel}
    >
      {Array.from({ length: count * 5 }, (_, index) => (
        <span
          className="alarm-wheel-number"
          key={index}
          data-selected={index % count === value}
          aria-hidden="true"
        >
          {String(index % count).padStart(2, "0")}
        </span>
      ))}
    </div>
  );
}

export default function SoundTimer({ timer }) {
  const [hours, setHours] = useState(0);
  const [minutes, setMinutes] = useState(15);
  const remainingMinutes = Math.floor(timer.remaining / 60);
  const display =
    String(remainingMinutes).padStart(2, "0") + ":" + String(timer.remaining % 60).padStart(2, "0");
  if (timer.running && !timer.starting)
    return (
      <div className="sound-countdown">
        <div className="sound-countdown-ring" role="timer" aria-label={"Осталось " + display}>
          <svg viewBox="0 0 140 140" aria-hidden="true">
            {Array.from({ length: 36 }, (_, index) => {
              const angle = (index / 36) * Math.PI * 2 - Math.PI / 2;
              return (
                <circle
                  key={index}
                  cx={70 + Math.cos(angle) * 58}
                  cy={70 + Math.sin(angle) * 58}
                  r={index < 3 ? 1.5 + index * 0.4 : 3}
                  fill={index / 36 < timer.progress ? "#bdbdb8" : "#d78a30"}
                />
              );
            })}
          </svg>
          <strong>{display}</strong>
        </div>
        <button type="button" className="sound-timer-cancel" onClick={timer.cancel}>
          Отмена
        </button>
      </div>
    );
  return (
    <>
      <div className="sound-duration-picker">
        <TimerColumn value={hours} count={24} label="Часы таймера" onChange={setHours} />
        <span className="sound-duration-unit">ч</span>
        <span className="sound-duration-colon">:</span>
        <TimerColumn value={minutes} count={60} label="Минуты таймера" onChange={setMinutes} />
        <span className="sound-duration-unit">мин</span>
      </div>
      <button
        type="button"
        className="sound-timer-start"
        data-started={timer.starting}
        disabled={hours * 60 + minutes === 0 || timer.starting}
        onClick={() => timer.start(hours * 60 + minutes)}
      >
        Запустить
      </button>
    </>
  );
}
