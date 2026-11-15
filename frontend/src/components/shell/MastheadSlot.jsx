import { createContext, useContext } from "react";
import { createPortal } from "react-dom";

// The masthead's page slot (#463). The consumer shell owns the masthead, but
// what sits beneath the wordmark (the feed's summary line and league pills,
// #464) depends on page data. A page renders that content where its data
// lives, inside <MastheadSlot>, and it appears under the wordmark:
//
//   <MastheadSlot>
//     <p>…summary line…</p>
//     <LeaguePills … />
//   </MastheadSlot>
//
// The slot sits inside the shell's `.signal-ui` scope, so its content gets the
// --sg-* tokens and the Signal UI type. It collapses when nothing is rendered
// into it. Outside the consumer shell (Ops, utility screens, the demo) there is
// no slot and <MastheadSlot> renders nothing.
export const MastheadSlotContext = createContext(null);

export default function MastheadSlot({ children }) {
  const node = useContext(MastheadSlotContext);
  return node ? createPortal(children, node) : null;
}
