import { describe, expect, it } from "vitest";
import { DEFAULT_GROUND, GROUND_STORAGE_KEY, normalizeGround, readGround, saveGround } from "./ground";

describe("ground preference", () => {
  it("defaults to white and accepts only the three grounds", () => {
    expect(DEFAULT_GROUND).toBe("light");
    for (const value of [undefined, null, "", "white", "DARK", "system", {}, 1]) {
      expect(normalizeGround(value)).toBe("light");
    }
    for (const value of ["light", "soft", "dark"]) expect(normalizeGround(value)).toBe(value);
  });

  it("reads the device preference synchronously, with white for missing or invalid data", () => {
    for (const value of ["light", "soft", "dark", null, "corrupt"]) {
      expect(readGround(() => ({ getItem: (key) => {
        expect(key).toBe(GROUND_STORAGE_KEY);
        return value;
      } }))).toBe(normalizeGround(value));
    }
  });

  it("persists a normalized choice that survives another read", () => {
    const values = new Map();
    const storage = () => ({
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    });
    for (const value of ["dark", "soft", "light", "corrupt"]) {
      expect(saveGround(value, storage)).toBe(normalizeGround(value));
      expect(readGround(storage)).toBe(normalizeGround(value));
    }
    expect([...values.keys()]).toEqual([GROUND_STORAGE_KEY]);
  });

  it("silently falls back to white if obtaining storage, reading, or writing throws", () => {
    const blocked = () => { throw new Error("SecurityError"); };
    expect(readGround(blocked)).toBe("light");
    expect(readGround(() => ({ getItem: blocked }))).toBe("light");
    expect(saveGround("dark", blocked)).toBe("light");
    expect(saveGround("soft", () => ({ setItem: blocked }))).toBe("light");
    expect(readGround(() => null)).toBe("light");
    expect(saveGround("dark", () => null)).toBe("light");
  });
});
