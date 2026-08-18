"use client";

import { useActionState } from "react";
import { changePassword, type SecurityState } from "./actions";
import { SubmitButton } from "@/app/studio/components/form-status";

const initial: SecurityState = { error: "" };
export function PasswordForm() {
  const [state, action] = useActionState(changePassword, initial);
  return <form action={action} className="account-password-form">
    <label>Current password<input name="current_password" type="password" autoComplete="current-password" required /></label>
    <label>New password<input name="new_password" type="password" autoComplete="new-password" minLength={12} required /></label>
    <SubmitButton>Change password</SubmitButton>
    {state.error && <p className="form-error" role="alert">{state.error}</p>}
    {state.success && <p className="form-success" role="status">{state.success}</p>}
  </form>;
}
