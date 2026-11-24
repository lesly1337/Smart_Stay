import { parseRoomIntent, findRequestedTrack } from "./roomIntent.js";
import { updateRoomSetting } from "./roomSettings.js";

export function applyRoomCommand(settings, text, devices, tracks = []) {
  if (/^(помощь|команды|что ты умеешь)[?.!\s]*$/i.test(text.trim())) {
    return {
      settings,
      message:
        "Можно менять все настройки карточек. Например: «яркость света 60 процентов», «тёплый свет», «температура 22 градуса», «закрой шторы», «включи шум дождя», «громкость 30 процентов», «таймер звука на 15 минут» (скажите «поставь таймер»), «будильник на 07:30» (скажите «поставь будильник»), «будильник только светом», «включи не беспокоить». Отмена: «отмени таймер звука», «выключи будильник».",
    };
  }
  const intent = parseRoomIntent(text);
  if (["brightness", "lightTone", "volume", "dnd"].includes(intent?.device)) {
    const device = intent.device === "volume" ? "sound" : intent.device === "dnd" ? "dnd" : "light";
    if (!devices?.[device])
      return { settings, message: "Настройки недоступны. Проверьте связь с симулятором." };
    const current = devices[device];
    const values = { ...current };
    let description;
    if (intent.device === "brightness") {
      values.brightness = Math.max(
        0,
        Math.min(100, intent.value ?? current.brightness + intent.delta),
      );
      description = `яркость ${values.brightness}%`;
    } else if (intent.device === "lightTone") {
      values.color_temperature_k = intent.tone === "warm" ? 2700 : 6500;
      description = intent.tone === "warm" ? "тёплый свет" : "холодный свет";
    } else if (intent.device === "volume") {
      values.volume = Math.max(0, Math.min(100, intent.value ?? current.volume + intent.delta));
      description = `громкость ${values.volume}%`;
    } else {
      values.enabled = intent.enabled;
      description = `режим «Не беспокоить»: ${intent.enabled ? "вкл" : "выкл"}`;
    }
    return {
      settings,
      device,
      values,
      message: `Запросил ${description}. Статус сохранения — в разделе «Управление».`,
    };
  }
  if (intent?.device === "alarm") {
    if (!devices?.alarm)
      return {
        settings,
        message: "Будильник недоступен. Проверьте связь с симулятором в разделе «Управление».",
      };
    const values = {
      ...devices.alarm,
      ...(intent.enabled !== undefined ? { enabled: intent.enabled } : {}),
      ...(intent.time ? { time: intent.time } : {}),
      ...(intent.mode ? { mode: intent.mode } : {}),
    };
    if (values.enabled && !values.time)
      return {
        settings,
        message: "Укажите время будильника, например: «поставь будильник на 07:30».",
      };
    return {
      settings,
      device: "alarm",
      values,
      message: `Запросил настройки будильника: ${values.enabled ? values.time : "выключен"}, режим — ${values.mode === "both" ? "свет и звук" : values.mode === "light" ? "свет" : "звук"}. Статус сохранения — в разделе «Управление».`,
    };
  }
  if (intent?.device === "soundTimer") {
    if (!devices?.sound)
      return {
        settings,
        message: "Таймер недоступен. Проверьте связь с симулятором в разделе «Управление».",
      };
    return {
      settings,
      soundTimerMinutes: intent.minutes,
      message: intent.minutes
        ? `Таймер звука запущен на ${intent.minutes} мин. Отсчёт — в карточке «Звук», статус сохранения — в разделе «Управление».`
        : "Таймер звука отменён. Статус сохранения — в разделе «Управление».",
    };
  }
  if (intent?.device === "sound") {
    if (!devices?.sound)
      return {
        settings,
        message: "Звук недоступен. Проверьте связь с симулятором в разделе «Управление».",
      };
    const sound = devices.sound;
    if (!intent.enabled)
      return {
        settings,
        device: "sound",
        values: { ...sound, volume: 0, timer_minutes: 0 },
        message: "Запросил выключение звука. Статус — в разделе «Управление».",
      };
    const generic =
      /^(пожалуйста )?(включи|включите|запусти|вруби) (звук|музыку)( пожалуйста)?$/.test(
        intent.query,
      );
    const track = generic
      ? tracks.find((item) => item.track_id === sound.track_id)
      : findRequestedTrack(intent.query, tracks);
    if (!track)
      return {
        settings,
        message:
          "Не удалось выбрать звук. Скажите, например: «включи шум дождя» или выберите трек в карточке «Звук».",
      };
    return {
      settings,
      device: "sound",
      values: { ...sound, track_id: track.track_id, volume: sound.volume > 0 ? sound.volume : 20 },
      message: `Запросил звук «${track.title}». Статус — в разделе «Управление».`,
    };
  }
  if (intent?.device === "climate") {
    if (!devices)
      return {
        settings,
        message: "Температура недоступна. Проверьте связь с симулятором в разделе «Управление».",
      };
    const temperature = Math.max(
      16,
      Math.min(26, Math.round(intent.value ?? devices.climate.temperature) + (intent.delta ?? 0)),
    );
    return {
      settings,
      device: "climate",
      values: { temperature },
      message: "Запрошено " + temperature + " °C. Статус — в разделе «Управление».",
    };
  }
  if (intent?.device === "light") {
    const enabled = intent.enabled;
    return {
      settings: updateRoomSetting(settings, "lightOn", enabled),
      message: enabled
        ? "Запросил включение света. Статус — в разделе «Управление»."
        : "Запросил выключение света. Статус — в разделе «Управление».",
    };
  }
  if (intent?.device === "curtains") {
    if (!devices)
      return {
        settings,
        message: "Шторы недоступны. Проверьте связь с симулятором в разделе «Управление».",
      };
    const position = intent.position;
    return {
      settings,
      device: "curtains",
      values: { position },
      message: position
        ? "Запросил открытие штор. Статус — в разделе «Управление»."
        : "Запросил закрытие штор. Статус — в разделе «Управление».",
    };
  }
  return {
    settings,
    message:
      "Не удалось однозначно понять настройку. Укажите одну настройку и её значение, например: «яркость света 60 процентов» или «поставь будильник на 07:30». Напишите «команды», чтобы увидеть примеры.",
  };
}
