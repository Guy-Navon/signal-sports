import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import ResultsBoard from "./ResultsBoard";
import GameDetailDialog from "./GameDetailDialog";
import ResultRow from "./ResultRow";
const game = { id: "g1", localDate: "2026-11-15", startTime: "2026-11-15T10:00:00Z", status: "final",
  sport: "basketball", competitionId: "comp:nba", competitionHe: "NBA", home: { name: "פורטלנד", score: 121, rank: 5, isWinner: true },
  away: { name: "סקרמנטו", score: 118, rank: 9 }, leaders: [{ side: "home", name: "דני אבדיה", value: 34, stat: "points" }],
  chosenPlayerLines: [], detailAvailable: true };
let view;
afterEach(() => { if (view) act(() => view.unmount()); view = null; });
const render = (props = {}) => act(() => { view = create(<ResultsBoard games={[game]} hasPreferences nowMs={Date.parse("2026-11-15T12:00:00Z")}
  getDetail={async () => ({ players: [], team_stats: {}, venue: null, attendance: null })} {...props} />); });

it("shows ranks, scorers and quiet winner emphasis, without fabricating a chosen line", () => {
  render(); const text = JSON.stringify(view.toJSON());
  for (const s of ["פורטלנד", "סקרמנטו", "[", "5", "34", "דני אבדיה"]) expect(text).toContain(s);
  expect(view.root.findAllByProps({ className: "sr-chosen-line" })).toHaveLength(0);
});
it("bounds the initial page and focuses the first newly revealed row", () => {
  const focus = vi.fn();
  act(() => { view = create(<ResultsBoard games={Array.from({ length: 41 }, (_, i) => ({ ...game, id: `g${String(i).padStart(2, "0")}` }))} hasPreferences getDetail={async () => ({})} />,
    { createNodeMock: element => ({ focus: element.props["data-game-id"] === "g40" ? focus : () => {} }) }); });
  expect(view.root.findAllByType(ResultRow)).toHaveLength(40);
  act(() => view.root.findAllByType("button").find(b => b.props.children === "הצג משחקים נוספים").props.onClick());
  expect(view.root.findAllByType(ResultRow)).toHaveLength(41);
  expect(focus).toHaveBeenCalledTimes(1);
});
it.each([[{ loading: true, games: [] }, "טוען"], [{ error: "down" }, "לא הצלחנו לטעון את התוצאות"],
  [{ hasPreferences: false }, "עדיין לא בחרת"], [{ games: [] }, "אין משחקים להיום"]])("renders intentional state %j", (props, text) => {
  render(props); expect(JSON.stringify(view.toJSON())).toContain(text);
});
it("supports retry and scores-only unavailable detail", () => {
  const retry = vi.fn(); render({ error: "down", onRetry: retry });
  act(() => view.root.findAllByType("button").find(b => b.props.children === "נסה שוב").props.onClick()); expect(retry).toHaveBeenCalled();
  act(() => view.unmount());
  render({ games: [{ ...game, detailAvailable: false, leaders: [] }] });
  expect(JSON.stringify(view.toJSON())).toContain("נתוני המשחק לא זמינים");
  expect(view.root.findAllByType(GameDetailDialog)).toHaveLength(0);
});
it("opens a popup from the actual row and restores its opener on close", () => {
  render(); const focus = vi.fn();
  const row = view.root.findAllByType("button").find(b => b.props["data-game-id"] === game.id);
  act(() => row.props.onClick({ currentTarget: { focus, isConnected: true } }));
  expect(view.root.findAllByType(GameDetailDialog)).toHaveLength(1);
  act(() => view.root.findByType(GameDetailDialog).props.onClose()); expect(focus).toHaveBeenCalled();
});
it("dialog loads full stats and uses native modal focus/escape semantics", async () => {
  const showModal = vi.fn(), close = vi.fn(), closed = vi.fn();
  await act(async () => { view = create(<GameDetailDialog game={game} onClose={closed} getDetail={async () => ({ venue: "Moda Center", attendance: 19000,
    team_stats: { home: { rebounds: 40 } }, players: [{ side: "home", name: "דני אבדיה", minutes: 35.5, stats: { points: 34, rebounds: 6, assists: 4, FG: "11-13" } }] })} />,
    { createNodeMock: element => element.type === "dialog" ? { showModal, close } : { focus() {} } }); });
  expect(showModal).toHaveBeenCalledTimes(1); expect(JSON.stringify(view.toJSON())).toContain("11-13");
  expect(JSON.stringify(view.toJSON())).toContain("Moda Center");
  act(() => view.root.findByType("dialog").props.onCancel({ preventDefault() {} })); expect(closed).toHaveBeenCalled();
});
it("dialog keeps close available through loading and a retryable detail failure", async () => {
  const getDetail = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce({ players: [], team_stats: {} });
  await act(async () => { view = create(<GameDetailDialog game={game} onClose={() => {}} getDetail={getDetail} />); });
  expect(JSON.stringify(view.toJSON())).toContain("לא הצלחנו לטעון את פרטי המשחק");
  await act(async () => view.root.findAllByType("button").find(b => b.props.children === "נסה שוב").props.onClick());
  expect(getDetail).toHaveBeenCalledTimes(2);
});
it("explicitly wraps Tab and Shift+Tab between the first and last modal controls", async () => {
  const first = { focus: vi.fn() }, last = { focus: vi.fn() };
  await act(async () => { view = create(<GameDetailDialog game={game} onClose={() => {}} getDetail={async () => ({ players: [], team_stats: {} })} />,
    { createNodeMock: element => element.type === "dialog" ? { showModal() {}, close() {} }
      : element.type === "summary" ? last : first }); });
  first.focus.mockClear();
  const preventDefault = vi.fn();
  act(() => view.root.findByType("dialog").props.onKeyDown({ key: "Tab", shiftKey: true, target: first, preventDefault }));
  expect(last.focus).toHaveBeenCalledTimes(1);
  act(() => view.root.findByType("dialog").props.onKeyDown({ key: "Tab", shiftKey: false, target: last, preventDefault }));
  expect(first.focus).toHaveBeenCalledTimes(1); expect(preventDefault).toHaveBeenCalledTimes(2);
});
