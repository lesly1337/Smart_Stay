import assert from "node:assert/strict";
import { test } from "node:test";
import {
  createSettingWriter,
  getDeviceSettings,
  getTracks,
  saveDevice,
} from "../FrontEnd/my-app/src/Front/api.js";
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("latest device changes are coalesced and writes remain serial", async () => {
  const calls = [],
    statuses = [];
  let busy = 0,
    maximum = 0;
  const writer = createSettingWriter(
    async (value) => {
      calls.push(value);
      maximum = Math.max(maximum, ++busy);
      await wait(25);
      busy--;
    },
    (status) => statuses.push(status),
    5,
  );
  writer.schedule({ enabled: true });
  writer.schedule({ enabled: false });
  await wait(12);
  writer.schedule({ enabled: true });
  await wait(100);
  assert.deepEqual(calls, [{ enabled: false }, { enabled: true }]);
  assert.equal(maximum, 1);
  assert.equal(statuses.at(-1), "saved");
  writer.dispose();
});
test("errors are reported and a retry can succeed", async () => {
  let fail = true;
  const statuses = [];
  const writer = createSettingWriter(
    async () => {
      if (fail) throw Error("offline");
    },
    (status, error) => statuses.push([status, error?.message]),
    1,
  );
  writer.schedule({ position: 100 });
  await wait(15);
  assert.deepEqual(statuses.at(-1), ["error", "offline"]);
  fail = false;
  writer.schedule({ position: 100 });
  await wait(15);
  assert.equal(statuses.at(-1)[0], "saved");
  writer.dispose();
});
test("device and track responses are validated before rendering", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({ ok: true, json: async () => null });
    await assert.rejects(getDeviceSettings());
    await assert.rejects(getTracks());
    globalThis.fetch = async (url) => ({
      ok: true,
      json: async () =>
        url.endsWith("/session")
          ? {
              run_id: "test-run",
              session_id: "test-session",
              at: "2026-11-12T18:30:00+03:00",
              expires_at: "2099-01-01T00:00:00Z",
            }
          : {
              light: { brightness: 70, color_temperature_k: 4000 },
              climate: { temperature: 20 },
              curtains: { position: 0 },
              sound: { track_id: "track_04", volume: 20 },
              alarm: { enabled: false, time: null, mode: "both" },
              dnd: { enabled: true },
            },
    });
    assert.equal((await getDeviceSettings()).alarm.time, null);
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/room/dnd");
      assert.deepEqual(JSON.parse(options.body), { enabled: false });
      return { ok: true, json: async () => ({ enabled: false }) };
    };
    assert.deepEqual(await saveDevice("dnd", { enabled: false }), { enabled: false });
    globalThis.fetch = async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: "Session required" }),
    });
    await assert.rejects(getDeviceSettings(), /Session required/);
  } finally {
    globalThis.fetch = original;
  }
});
