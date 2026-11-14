import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, it } from "vitest";
import LegacyPreferencesRedirect from "./LegacyPreferencesRedirect";

function Destination() {
  const location = useLocation();
  return <output>{location.pathname}{location.search}{location.hash}</output>;
}

it.each([
  ["/calibration", "/preferences/calibration"],
  ["/interests", "/preferences"],
])("redirects the mounted legacy %s route with its complete query and anchor", (old, target) => {
  /** @type {import("react-test-renderer").ReactTestRenderer} */
  let renderer;
  act(() => {
    renderer = create(
      <MemoryRouter initialEntries={[`${old}?from=email&tag=a%2Fb&tag=c+v#cal-item-a`]}>
        <Routes>
          <Route path={old} element={<LegacyPreferencesRedirect />} />
          <Route path="/preferences/*" element={<Destination />} />
        </Routes>
      </MemoryRouter>,
    );
  });
  expect(renderer.root.findByType("output").children.join("")).toBe(`${target}?from=email&tag=a%2Fb&tag=c+v#cal-item-a`);
  act(() => renderer.unmount());
});
