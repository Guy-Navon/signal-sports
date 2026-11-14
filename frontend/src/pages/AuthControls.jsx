import React from "react";
import { Button as BaseButton } from "@/components/ui/button";
import { Input as BaseInput } from "@/components/ui/input";
import { Label as BaseLabel } from "@/components/ui/label";
import "./account-auth.css";

// Explicit, local opt-in: the shared primitives and Ops retain their styles.
export const Button = React.forwardRef(
  /** @param {Record<string, any>} props */
  ({ className = "", variant = "default", ...props }, ref) => (
    <BaseButton ref={ref} variant={variant} data-auth-variant={variant}
      className={`sg-auth-button ${className}`} {...props} />
  ),
);
Button.displayName = "AuthButton";

export const Input = React.forwardRef(
  /** @param {Record<string, any>} props */
  ({ className = "", ...props }, ref) => (
    <BaseInput ref={ref} className={`sg-auth-input ${className}`} {...props} />
  ),
);
Input.displayName = "AuthInput";

export const Label = React.forwardRef(
  /** @param {Record<string, any>} props */
  ({ className = "", ...props }, ref) => (
    <BaseLabel ref={ref} className={`sg-auth-label ${className}`} {...props} />
  ),
);
Label.displayName = "AuthLabel";
