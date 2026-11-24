import { parseCardCommand } from "./cardCommands.js";
// Deliberately conservative: unclear or negated requests must not change devices.
export function parseRoomIntent(text) {
  const card = parseCardCommand(text);
  if (card) return card;
  // Invalid values must not fall through to an unrelated toggle.
  if (/\d/.test(text) && !/будильник|таймер/i.test(text)) return null;
  const command = text
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^а-яa-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const has = (pattern) => pattern.test(command);
  if (has(/(^| )(не|нельзя|никогда|отмена)( |$)/)) return null;
  if (has(/будильник/)) {
    if (has(/таймер|штор|температур/)) return null;
    const off = has(/отмени|отменить|выключ|отключ|убери/);
    const on = has(/постав|ставь|установ|заведи|включ/);
    if (off && !on) return { device: "alarm", enabled: false };
    if (!on || off) return null;
    const time = command.match(
      /(?:на|в) (\d{1,2})(?: (\d{1,2}))?(?: (?:час|часа|часов))?(?: (утра|вечера|дня|ночи))?(?: пожалуйста)?$/,
    );
    if (!time) return null;
    let hour = Number(time[1]);
    const minute = Number(time[2] || 0);
    if (hour > 23 || minute > 59) return null;
    if (time[3] && (hour < 1 || hour > 12)) return null;
    if (time[3] === "вечера" || time[3] === "дня") hour = (hour % 12) + 12;
    if (time[3] === "утра" || time[3] === "ночи") hour %= 12;
    return {
      device: "alarm",
      enabled: true,
      time: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
    };
  }
  if (has(/таймер/)) {
    if (has(/свет|штор|будильник|температур/)) return null;
    if (has(/отмени|убери|выключи|отключи|останови/)) return { device: "soundTimer", minutes: 0 };
    if (!has(/ставь|установи|запусти|включи/)) return null;
    let duration = command;
    const numbers = {
      пятнадцать: 15,
      тридцать: 30,
      двадцать: 20,
      сорок: 40,
      шестьдесят: 60,
      десять: 10,
      пять: 5,
      один: 1,
      одну: 1,
      два: 2,
      две: 2,
    };
    for (const [word, value] of Object.entries(numbers))
      duration = duration.replace(new RegExp(`(^| )${word}(?= |$)`, "g"), `$1${value}`);
    duration = duration.replace(/полчаса/g, "30 минут").replace(/на час(?= |$)/g, "на 1 час");
    const amount = duration.match(/на (\d+) (минут[а-я]*|час[а-я]*)(?: и (\d+) минут[а-я]*)?/);
    if (!amount) return null;
    const minutes =
      Number(amount[1]) * (amount[2].startsWith("час") ? 60 : 1) + Number(amount[3] || 0);
    return minutes > 0 && minutes <= 1439 ? { device: "soundTimer", minutes } : null;
  }
  const intents = [];
  if (
    has(
      /звук|музык|шум|дожд|прибой|океан|моря|камин|костер|птиц|фортепиано|пианино|ветер|сосн|ручей|чаш|ночной город|приветствие/,
    )
  ) {
    const on = has(/(^| )(включ|запусти|поставь|воспроизведи|вруби)/);
    const off = has(/выключ|отключ|останови|выруби|убери/);
    if (on !== off) intents.push({ device: "sound", enabled: on, query: command });
  }
  if (has(/свет|освещ|ламп/)) {
    const off = has(/выключ|отключ|погас|потуш|выруби|убери/);
    const on = has(/(^| )(включ|зажг|зажеч|вруби|запусти|верни)/);
    if (off !== on) intents.push({ device: "light", enabled: on });
  }
  if (has(/штор|жалюзи/)) {
    const open = has(/откр|раздвин|подними|поднять/);
    const close = has(/закр|задвин|задерни|задернуть|опусти|опустить/);
    if (open !== close) intents.push({ device: "curtains", position: open ? 100 : 0 });
  }
  const warmer = has(
    /теплее|потеплее|мне холодно|холодно в номере|прибавь температур|подними температур|повыс[ьи] температур/,
  );
  const cooler = has(
    /прохладнее|похолоднее|холоднее|мне жарко|жарко в номере|убавь температур|пониз[ьи] температур|сниз[ьи] температур/,
  );
  if (warmer !== cooler) intents.push({ device: "climate", delta: warmer ? 1 : -1 });
  return intents.length === 1 ? intents[0] : null;
}

export function findRequestedTrack(query, tracks) {
  const aliases = [
    [/дожд/, /дожд/],
    [/прибой|океан|моря/, /прибой/],
    [/белый шум|белого шума/, /белый шум/],
    [/розов/, /розов/],
    [/камин|костер/, /камин/],
    [/птиц/, /птиц/],
    [/фортепиано|пианино/, /фортепиано/],
    [/ветер|сосн/, /сосн/],
    [/ручей|ручья/, /ручей/],
    [/чаш/, /чаш/],
    [/ночной город/, /ночной город/],
    [/приветствие/, /приветствие/],
  ];
  const matched = aliases.filter(([pattern]) => pattern.test(query));
  if (matched.length !== 1) return null;
  return (
    tracks.find((track) => matched[0][1].test(track.title.toLowerCase().replace(/ё/g, "е"))) || null
  );
}
