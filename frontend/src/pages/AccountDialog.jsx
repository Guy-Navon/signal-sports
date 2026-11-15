import React from "react";
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import "./account-auth.css";

// A portal needs its own token scope. Keep Radix's focus trap, cancellation,
// accessible title/description and trigger focus restoration without changing
// the shared dialog or the Ops overlay.
export function AccountDialogContent({ children }) {
  return (
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Overlay className="signal-ui sg-account-overlay" />
      <AlertDialogPrimitive.Content dir="rtl" className="signal-ui sg-account-dialog">
        {children}
      </AlertDialogPrimitive.Content>
    </AlertDialogPrimitive.Portal>
  );
}
