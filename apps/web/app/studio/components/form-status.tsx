"use client";
import { useFormStatus } from "react-dom";
export function SubmitButton({ children }: { children: string }) {
  const { pending } = useFormStatus();
  return (
    <button className="studio-primary" disabled={pending} type="submit">
      {pending ? "Saving…" : children}
    </button>
  );
}
