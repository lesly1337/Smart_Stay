import { useAlarmWheel } from "./Menu.js";

function TimeColumn({ value, count, label, onChange }) {
  const wheel = useAlarmWheel(value, count, onChange);
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
      {Array.from({ length: count * 5 }, (_, number) => (
        <span
          className="alarm-wheel-number"
          data-selected={number % count === value}
          key={number}
          aria-hidden="true"
        >
          {String(number % count).padStart(2, "0")}
        </span>
      ))}
    </div>
  );
}

export default function AlarmTimePicker({ value, onChange }) {
  const [hours, minutes] = value.split(":").map(Number);
  return (
    <div className="alarm-time-picker">
      <TimeColumn
        label="Часы"
        count={24}
        value={hours}
        onChange={(number) => onChange("hours", number)}
      />
      <TimeColumn
        label="Минуты"
        count={60}
        value={minutes}
        onChange={(number) => onChange("minutes", number)}
      />
    </div>
  );
}
