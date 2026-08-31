"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useFormStatus } from "react-dom";

export function AccountSubmitButton({
  children,
  pendingLabel = "Saving…",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode; pendingLabel?: string }) {
  const { pending } = useFormStatus();
  return (
    <button {...props} aria-busy={pending} disabled={pending || props.disabled} type="submit">
      {pending ? pendingLabel : children}
    </button>
  );
}
