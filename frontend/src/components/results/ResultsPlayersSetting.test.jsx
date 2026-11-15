import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import ResultsPlayersSetting, { ResultsPlayersEditor } from "./ResultsPlayersSetting";
import { getMeResultsPlayers, getResultsPlayersCatalog, putMeResultsPlayers } from "@/api/client";
vi.mock("@/api/client", () => ({ getMeResultsPlayers: vi.fn(), getResultsPlayersCatalog: vi.fn(), putMeResultsPlayers: vi.fn() }));
let view;
afterEach(() => { if (view) act(() => view.unmount()); view = null; vi.resetAllMocks(); });
const player = { entity_id: "player:deni_avdija", name: "דני אבדיה", name_en: "Deni Avdija", aliases: [] };

it("offers add/remove chips and explicit save without feed controls", () => {
  const change = vi.fn(), save = vi.fn();
  act(() => { view = create(<ResultsPlayersEditor catalog={[player]} selected={[]} onChange={change} onSave={save} />); });
  act(() => view.root.findAllByType("button").find(b => b.props["aria-label"] === "הוספת דני אבדיה").props.onClick());
  expect(change).toHaveBeenCalledWith([player.entity_id]);
  act(() => view.update(<ResultsPlayersEditor catalog={[player]} selected={[player.entity_id]} onChange={change} onSave={save} />));
  act(() => view.root.findAllByType("button").find(b => b.props["aria-label"] === "הסרת דני אבדיה").props.onClick());
  expect(change).toHaveBeenLastCalledWith([]);
  act(() => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  expect(save).toHaveBeenCalled();
});

it("does not call an API in local/read-only mode", async () => {
  await act(async () => { view = create(<ResultsPlayersSetting enabled={false} />); });
  expect(getMeResultsPlayers).not.toHaveBeenCalled();
  expect(getResultsPlayersCatalog).not.toHaveBeenCalled();
});

it("loads own choices, sends only ids, refreshes only results and handles failed save", async () => {
  vi.mocked(getMeResultsPlayers).mockResolvedValue({ players: [] });
  vi.mocked(getResultsPlayersCatalog).mockResolvedValue({ players: [player] });
  vi.mocked(putMeResultsPlayers).mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce({ players: [player] });
  const saved = vi.fn();
  await act(async () => { view = create(<ResultsPlayersSetting enabled onSaved={saved} />); });
  act(() => view.root.findByType(ResultsPlayersEditor).props.onChange([player.entity_id]));
  await act(async () => view.root.findByType(ResultsPlayersEditor).props.onSave());
  expect(JSON.stringify(view.toJSON())).toContain("השמירה נכשלה");
  await act(async () => view.root.findByType(ResultsPlayersEditor).props.onSave());
  expect(putMeResultsPlayers).toHaveBeenLastCalledWith([player.entity_id]);
  expect(saved).toHaveBeenCalledTimes(1);
});
