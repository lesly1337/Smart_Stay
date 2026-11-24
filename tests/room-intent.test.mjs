import test from "node:test";
import assert from "node:assert/strict";
import { parseRoomIntent } from "../FrontEnd/my-app/src/Front/roomIntent.js";
import { applyRoomCommand } from "../FrontEnd/my-app/src/Front/roomCommands.js";

test("all card settings can be changed without losing other device fields", () => {
  const settings = { brightness: 40, lightOn: true, lightTone: "warm" };
  const devices = {
    light: { brightness: 40, color_temperature_k: 4000 },
    climate: { temperature: 23 },
    curtains: { position: 0 },
    sound: { track_id: "rain", volume: 30, timer_minutes: 15 },
    alarm: { enabled: true, time: "07:30", mode: "both" },
    dnd: { enabled: false },
  };
  const cases = [
    ["Яркость света 60 процентов", "light", { brightness: 60, color_temperature_k: 4000 }],
    ["Свет на 0 процентов", "light", { brightness: 0, color_temperature_k: 4000 }],
    ["Сделай свет ярче", "light", { brightness: 50, color_temperature_k: 4000 }],
    ["Приглуши свет", "light", { brightness: 30, color_temperature_k: 4000 }],
    ["Сделай свет теплым", "light", { brightness: 40, color_temperature_k: 2700 }],
    ["Холодный свет", "light", { brightness: 40, color_temperature_k: 6500 }],
    ["Поставь температуру 22 градуса", "climate", { temperature: 22 }],
    ["Температура 22,5 градуса", "climate", { temperature: 23 }],
    ["Громкость 80 процентов", "sound", { track_id: "rain", volume: 80, timer_minutes: 15 }],
    ["Сделай потише", "sound", { track_id: "rain", volume: 20, timer_minutes: 15 }],
    ["Сделай погромче", "sound", { track_id: "rain", volume: 40, timer_minutes: 15 }],
    ["Будильник только светом", "alarm", { enabled: true, time: "07:30", mode: "light" }],
    ["Будильник только звуком", "alarm", { enabled: true, time: "07:30", mode: "sound" }],
    ["Будильник свет и звук", "alarm", { enabled: true, time: "07:30", mode: "both" }],
    ["Выключи будильник", "alarm", { enabled: false, time: "07:30", mode: "both" }],
    ["Включи не беспокоить", "dnd", { enabled: true }],
    ["Выключи режим не беспокоить", "dnd", { enabled: false }],
  ];
  for (const [text, device, values] of cases) {
    const result = applyRoomCommand(settings, text, devices);
    assert.equal(result.device, device, text);
    assert.deepEqual(result.values, values, text);
    assert.equal(result.settings, settings, text);
  }
});

test("card parameters reject out-of-range values, negations and missing state", () => {
  for (const phrase of [
    "Громкость 101",
    "Яркость -10",
    "Температура 30",
    "Свет на 150 процентов",
    "Не включай не беспокоить",
    "Не меняй громкость на 20",
    "Будильник на 29:99",
    "Яркость 20 и громкость 80",
  ]) {
    assert.equal(parseRoomIntent(phrase), null, phrase);
  }
  assert.equal(applyRoomCommand({}, "Громкость 50", null).device, undefined);
  assert.equal(
    applyRoomCommand({}, "Включи будильник", {
      alarm: { time: null, mode: "both", enabled: false },
    }).device,
    undefined,
  );
});

test("alarm voice request handles screenshot time and preserves alarm mode", () => {
  const devices = { alarm: { enabled: false, time: null, mode: "both" } };
  for (const phrase of [
    "поставить будильник на 15-30",
    "Поставь будильник на 15:30",
    "Установи будильник на 15 30",
  ]) {
    assert.deepEqual(applyRoomCommand({}, phrase, devices).values, {
      enabled: true,
      time: "15:30",
      mode: "both",
    });
  }
  assert.equal(parseRoomIntent("Поставь будильник на 7 утра").time, "07:00");
  assert.equal(parseRoomIntent("Поставь будильник на 7 вечера").time, "19:00");
  assert.equal(applyRoomCommand({}, "Выключи будильник", devices).values.enabled, false);
  for (const phrase of [
    "Не ставь будильник на 15:30",
    "Поставь будильник на 25:30",
    "Поставь будильник на 15:80",
    "Поставь будильник",
    "Выключи и включи будильник",
  ])
    assert.equal(parseRoomIntent(phrase), null, phrase);
  assert.equal(applyRoomCommand({}, "Поставь будильник на 15:30", null).device, undefined);
});

test("sound timer uses shared countdown action, not a sound toggle", () => {
  const settings = {};
  const devices = { sound: { volume: 20 } };
  for (const phrase of [
    "Ставь таймер звуку на 15 минут.",
    "Поставь таймер звука на пятнадцать минут",
    "Установи таймер на 15 минут",
  ]) {
    const result = applyRoomCommand(settings, phrase, devices);
    assert.equal(result.soundTimerMinutes, 15, phrase);
    assert.equal(result.device, undefined);
  }
  assert.equal(applyRoomCommand(settings, "Отмени таймер звука", devices).soundTimerMinutes, 0);
  assert.equal(parseRoomIntent("Поставь таймер на полчаса").minutes, 30);
  assert.equal(parseRoomIntent("Поставь таймер на час").minutes, 60);
  for (const phrase of [
    "Не ставь таймер на 15 минут",
    "Поставь таймер на 0 минут",
    "Поставь таймер на 9999 минут",
    "Поставь таймер на сколько-нибудь минут",
  ])
    assert.equal(parseRoomIntent(phrase), null);
  assert.equal(
    applyRoomCommand(settings, "Поставь таймер на 15 минут", null).soundTimerMinutes,
    undefined,
  );
});

test("voice sound request selects actual catalog ID and enables volume", () => {
  const settings = { brightness: 70, lightOn: true };
  const devices = { sound: { track_id: "old", volume: 0, timer_minutes: 0 } };
  const tracks = [{ track_id: "actual-rain-id", title: "Шум дождя" }];
  const result = applyRoomCommand(settings, "Включи звук шум дождя.", devices, tracks);
  assert.equal(result.device, "sound");
  assert.deepEqual(result.values, { track_id: "actual-rain-id", volume: 20, timer_minutes: 0 });
  assert.equal(result.settings, settings);
  assert.equal(
    applyRoomCommand(settings, "Не включай шум дождя", devices, tracks).device,
    undefined,
  );
  assert.equal(applyRoomCommand(settings, "Включи шум дождя", devices, []).device, undefined);
  assert.equal(applyRoomCommand(settings, "Включи музыку джаз", devices, tracks).device, undefined);
  assert.equal(applyRoomCommand(settings, "Выключи звук", devices, tracks).values.volume, 0);
});

test("natural light requests with polite words and synonyms", () => {
  for (const phrase of [
    "Выключи свет.",
    "Погаси, пожалуйста, свет",
    "Можешь отключить освещение?",
    "Потуши лампу",
    "Свет выруби",
  ]) {
    assert.deepEqual(parseRoomIntent(phrase), { device: "light", enabled: false }, phrase);
  }
  assert.deepEqual(parseRoomIntent("Зажги свет, пожалуйста"), { device: "light", enabled: true });
});
test("temperature and curtain paraphrases", () => {
  assert.deepEqual(parseRoomIntent("Мне холодно"), { device: "climate", delta: 1 });
  assert.deepEqual(parseRoomIntent("Сделай немного прохладнее"), { device: "climate", delta: -1 });
  assert.deepEqual(parseRoomIntent("Задёрни шторы"), { device: "curtains", position: 0 });
  assert.deepEqual(parseRoomIntent("Раздвинь шторы"), { device: "curtains", position: 100 });
});
test("negated, conflicting and unrelated utterances do not issue commands", () => {
  for (const phrase of [
    "Не выключай свет",
    "Свет не включай",
    "Выключи и включи свет",
    "Открой шторы и погаси свет",
    "Привет",
    "Света пришла",
    "Не надо делать теплее",
  ]) {
    assert.equal(parseRoomIntent(phrase), null, phrase);
  }
});
