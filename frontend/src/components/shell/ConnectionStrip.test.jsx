import React from "react";
import { act, create } from "react-test-renderer";
import { expect, it, vi } from "vitest";
import ConnectionStrip from "@/components/shell/ConnectionStrip";
import { connectionErrorStrip } from "@/components/feed/feedLoadModel";

it("announces the consumer connection error and retries from a real button", () => {
  const onRetry = vi.fn();
  /** @type {import("react-test-renderer").ReactTestRenderer} */
  let renderer = /** @type {any} */ (null);
  act(() => {
    renderer = create(<ConnectionStrip {...connectionErrorStrip({ area: "product", message: "boom" })} onRetry={onRetry} />);
  });
  const root = renderer.root;
  expect(root.findByProps({ className: "sg-conn" }).props.role).toBe("alert");
  const text = JSON.stringify(renderer.toJSON());
  expect(text).toContain("שגיאה בחיבור לשרת");
  expect(text).toContain("חלק מהמידע לא נטען");
  expect(text).not.toContain("boom");
  const button = root.findByType("button");
  expect(button.props.type).toBe("button");
  act(() => button.props.onClick());
  expect(onRetry).toHaveBeenCalledTimes(1);
  act(() => renderer.unmount());
});
