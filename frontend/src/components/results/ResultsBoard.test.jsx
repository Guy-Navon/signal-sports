import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import ResultsBoard from "./ResultsBoard";
import GameDetailDialog from "./GameDetailDialog";
import ResultRow from "./ResultRow";
import ResultTile from "./ResultTile";

const NOW = Date.parse("2026-11-15T12:00:00Z");
const side = (id, name, score, extra = {}) => ({ id, name, score, rank: null, isWinner: false, ...extra });
const game = { id: "g1", localDate: "2026-11-14", startTime: "2026-11-14T03:00:00Z", status: "final", winner: "home",
  sport: "basketball", competitionId: "comp:nba", competitionHe: "NBA", home: side("team:portland_blazers", "פורטלנד בלייזרס", 121, { rank: 5, isWinner: true }),
  away: side("team:sacramento_kings", "סקרמנטו קינגס", 118, { rank: 9 }), leaders: [{ side: "home", name: "דני אבדיה", value: 34, stat: "points" }],
  chosenPlayerLines: [{ side: "home", name: "דני אבדיה", entity_id: "player:deni_avdija", minutes: 35, stats: { points: 34, rebounds: 6, assists: 4 } }],
  relevanceReason: "", detailAvailable: true };
const detail = { venue: "Moda Center", attendance: 19000, team_stats: { home: { quarters: [30, 30, 30, 31] }, away: { quarters: [30, 30, 30, 28] } },
  players: [{ side: "home", name: "דני אבדיה", minutes: 35.5, stats: { points: 34, rebounds: 6, assists: 4, FG: "11-13", "3PT": "2-4", FT: "10-10", starter: true } }] };
let view;
afterEach(() => { if (view) act(() => view.unmount()); view = null; });
const render = (props = {}, options) => act(() => { view = create(<ResultsBoard games={[game]} hasPreferences nowMs={NOW}
  getDetail={async () => detail} {...props} />, options); });
const text = () => JSON.stringify(view.toJSON());
const labelOf = node => node.findAll(() => true).flatMap(n => n.children.filter(c => typeof c === "string")).join("");
const buttons = label => view.root.findAllByType("button").filter(b => labelOf(b).includes(label));
const dialogNodes = element => element.type === "dialog" ? { showModal() {}, close() {} } : { focus() {} };

it("renders a tile for a chosen-player game, the stream row, the players box and no invented tiles", () => {
  render();
  expect(view.root.findAllByType(ResultTile)).toHaveLength(1);
  expect(view.root.findAllByType(ResultRow)).toHaveLength(1);
  for (const s of ["הקבוצות שלך", "השחקנים שלך", "פורטלנד", "סקרמנטו", "34 נק׳ · 6 ריב׳ · 4 אס׳", "בחירת שחקנים לתוצאות"]) expect(text()).toContain(s);
  expect(text()).not.toContain("הערב");
  act(() => view.unmount());
  render({ games: [{ ...game, chosenPlayerLines: [] }] });
  expect(view.root.findAllByType(ResultTile)).toHaveLength(0);
  expect(text()).not.toContain("הקבוצות שלך");
});
it("shows the followed-team dot on a followed team and the tile verdict", () => {
  render({ games: [{ ...game, chosenPlayerLines: [] }], profile: { profileV2: { scope_affinities: [{ scope: "team", target_id: "team:portland_blazers", level: 1, source: "explicit" }] } } });
  expect(view.root.findAllByProps({ className: "sr-dot" })).toHaveLength(2);
  expect(text()).toContain("ניצחון");
});
it("collapses a league above five games and focuses the first revealed row", () => {
  const focus = vi.fn();
  const games = Array.from({ length: 8 }, (_, i) => ({ ...game, id: `g${i}`, chosenPlayerLines: [], startTime: `2026-11-14T0${i}:00:00Z` }));
  render({ games }, { createNodeMock: element => ({ focus: element.props["data-game-id"] === "g3" ? focus : () => {} }) });
  expect(view.root.findAllByType(ResultRow)).toHaveLength(4);
  const more = buttons("עוד 4 משחקי")[0];
  expect(more.props["aria-expanded"]).toBe("false");
  act(() => more.props.onClick());
  expect(view.root.findAllByType(ResultRow)).toHaveLength(8);
  expect(focus).toHaveBeenCalledTimes(1);
  expect(buttons("עוד")).toHaveLength(0);
});
it("lists tonight's scheduled games outside the stream, then upcoming ones under הקרוב, and nothing else", () => {
  const sched = (id, date) => ({ ...game, id, status: "scheduled", winner: null, localDate: date, startTime: `${date}T17:00:00Z`, chosenPlayerLines: [],
    home: side("team:a", "בית", null), away: side("team:b", "חוץ", null), detailAvailable: false });
  render({ games: [game, sched("s1", "2026-11-15")] });
  expect(text()).toContain("הערב"); expect(view.root.findAllByType(ResultRow)).toHaveLength(1);
  act(() => view.unmount());
  render({ games: [game, sched("s2", "2026-11-16")] });
  expect(text()).toContain("הקרוב");
  act(() => view.unmount());
  render({ games: [game] });
  expect(text()).not.toContain("הקרוב");
});
it.each([[{ loading: true, games: [] }, "טוען"], [{ error: "down" }, "לא הצלחנו לטעון את התוצאות"],
  [{ hasPreferences: false }, "עדיין לא בחרת"], [{ games: [] }, "אין משחקים להיום"]])("renders intentional state %j", (props, expected) => {
  render(props); expect(text()).toContain(expected);
});
it("supports retry and scores-only unavailable detail", () => {
  const retry = vi.fn(); render({ error: "down", onRetry: retry });
  act(() => buttons("נסה שוב")[0].props.onClick()); expect(retry).toHaveBeenCalled();
  act(() => view.unmount());
  render({ games: [{ ...game, detailAvailable: false, leaders: [] }] });
  expect(text()).toContain("תוצאה בלבד");
  expect(view.root.findAllByType(GameDetailDialog)).toHaveLength(0);
  expect(view.root.findAllByType("button").filter(b => b.props["data-game-id"])).toHaveLength(0);
});
it("opens the popup from a row and from a tile and restores the opener on close", () => {
  render(); const focus = vi.fn();
  for (const Type of [ResultRow, ResultTile]) {
    act(() => view.root.findByType(Type).findByType("button").props.onClick({ currentTarget: { focus, isConnected: true } }));
    expect(view.root.findAllByType(GameDetailDialog)).toHaveLength(1);
    act(() => view.root.findByType(GameDetailDialog).props.onClose());
    expect(focus).toHaveBeenCalled(); focus.mockClear();
  }
});
it("popup shows scoreboard, quarter table, box score with the top scorer and venue, and uses native modal semantics", async () => {
  const showModal = vi.fn(), closed = vi.fn();
  await act(async () => { view = create(<GameDetailDialog game={game} onClose={closed} getDetail={async () => detail} />,
    { createNodeMock: element => element.type === "dialog" ? { showModal, close: vi.fn() } : { focus() {} } }); });
  expect(showModal).toHaveBeenCalledTimes(1);
  for (const s of ["Moda Center", "19,000", "סיום", "רבע ", "דני אבדיה", "9/9", "10/10", "2/4", "חמישייה"]) expect(text()).toContain(s);
  expect(view.root.findAllByProps({ role: "tab" }).filter(n => typeof n.type === "string")).toHaveLength(2);
  expect(view.root.findByProps({ "data-top": true })).toBeTruthy();
  act(() => view.root.findByType("dialog").props.onCancel({ preventDefault() {} })); expect(closed).toHaveBeenCalled();
});
it("popup switches team tabs and moves with arrow keys", async () => {
  await act(async () => { view = create(<GameDetailDialog game={game} onClose={() => {}} getDetail={async () => ({ ...detail, players: [...detail.players,
    { side: "away", name: "Domantas Sabonis", minutes: 30, stats: { points: 20, starter: true } }] })} />, { createNodeMock: dialogNodes }); });
  const tabs = () => view.root.findAllByProps({ role: "tab" }).filter(n => typeof n.type === "string");
  expect(tabs()[0].props["aria-selected"]).toBe(true);
  act(() => tabs()[1].props.onClick());
  expect(text()).toContain("Domantas Sabonis"); expect(text()).not.toContain("11/13");
  const preventDefault = vi.fn();
  act(() => tabs()[1].props.onKeyDown({ key: "ArrowLeft", preventDefault }));
  expect(preventDefault).toHaveBeenCalled();
  expect(tabs()[0].props["aria-selected"]).toBe(true);
});
it("popup shows football scorers and skips the basketball parts", async () => {
  const football = { ...game, sport: "football", competitionHe: "ליגת העל", chosenPlayerLines: [], leaders: [] };
  await act(async () => { view = create(<GameDetailDialog game={football} onClose={() => {}} getDetail={async () => ({ team_stats: {}, players: [
    { side: "home", name: "אסטר סוקלר", stats: { goals: 1, yellow_cards: 1 } }] })} />, { createNodeMock: dialogNodes }); });
  expect(text()).toContain("אסטר סוקלר"); expect(text()).toContain("כרטיס צהוב");
  expect(view.root.findAllByProps({ role: "tab" })).toHaveLength(0);
  expect(text()).not.toContain("נקודות");
});
it("popup keeps close available through loading and a retryable detail failure", async () => {
  const getDetail = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce({ players: [], team_stats: {} });
  await act(async () => { view = create(<GameDetailDialog game={game} onClose={() => {}} getDetail={getDetail} />); });
  expect(text()).toContain("לא הצלחנו לטעון את פרטי המשחק");
  await act(async () => view.root.findAllByType("button").find(b => b.props.children === "נסה שוב").props.onClick());
  expect(getDetail).toHaveBeenCalledTimes(2);
});
it("explicitly wraps Tab and Shift+Tab between the close button and the last focusable control", async () => {
  const first = { focus: vi.fn(), tabIndex: 0 }, last = { focus: vi.fn(), tabIndex: 0 };
  await act(async () => { view = create(<GameDetailDialog game={game} onClose={() => {}} getDetail={async () => detail} />,
    { createNodeMock: element => element.type === "dialog" ? { showModal() {}, close() {}, querySelectorAll: () => [first, last] }
      : element.props["aria-label"] === "סגירת פרטי המשחק" ? first : { focus() {} } }); });
  first.focus.mockClear();
  const preventDefault = vi.fn();
  act(() => view.root.findByType("dialog").props.onKeyDown({ key: "Tab", shiftKey: true, target: first, preventDefault }));
  expect(last.focus).toHaveBeenCalledTimes(1);
  act(() => view.root.findByType("dialog").props.onKeyDown({ key: "Tab", shiftKey: false, target: last, preventDefault }));
  expect(first.focus).toHaveBeenCalledTimes(1); expect(preventDefault).toHaveBeenCalledTimes(2);
});
