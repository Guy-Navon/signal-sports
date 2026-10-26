import { describe, expect, it } from "vitest";
import { menuDismissAction } from "./menuDismissModel";

describe("menuDismissAction (journey audit D9)", () => {
  it("Escape closes and returns focus to the button that opened the menu", () => {
    expect(menuDismissAction({ type: "keydown", key: "Escape", inside: true }))
      .toEqual({ close: true, restoreFocus: true });
  });

  it("a tap or click outside closes without stealing focus from where it landed", () => {
    expect(menuDismissAction({ type: "pointerdown", inside: false }))
      .toEqual({ close: true, restoreFocus: false });
  });

  it("a tap inside the menu, or any other key, leaves it open", () => {
    expect(menuDismissAction({ type: "pointerdown", inside: true })).toEqual({ close: false, restoreFocus: false });
    expect(menuDismissAction({ type: "keydown", key: "Tab", inside: true })).toEqual({ close: false, restoreFocus: false });
  });
});
