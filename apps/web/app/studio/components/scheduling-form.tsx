"use client";

import { useActionState } from "react";
import { scheduleTitleAction, type FormState } from "@/app/studio/actions";
import { SubmitButton } from "@/app/studio/components/form-status";

const initial: FormState = { error: "" };
function utcInput(value: string | null) { return value ? value.slice(0, 16) : ""; }

export function SchedulingForm({ kind, id, schedule }: {
  kind: "movies" | "series"; id: string;
  schedule: { publish_at: string | null; unpublish_at: string | null; rights_start_at: string | null; rights_end_at: string | null };
}) {
  const [state, action] = useActionState(scheduleTitleAction.bind(null, kind, id), initial);
  return <section className="studio-editor-section"><div className="form-section-heading"><div><p className="eyebrow">Distribution</p><h2>Publishing & rights</h2></div><span>UTC</span></div>
    <form action={action} className="homepage-rail-form">
      <label>Publish later (UTC)<input type="datetime-local" name="publish_at" defaultValue={utcInput(schedule.publish_at)} /></label>
      <label>Unpublish later (UTC)<input type="datetime-local" name="unpublish_at" defaultValue={utcInput(schedule.unpublish_at)} /></label>
      <label>Rights start (UTC)<input type="datetime-local" name="rights_start_at" defaultValue={utcInput(schedule.rights_start_at)} /></label>
      <label>Rights end (UTC)<input type="datetime-local" name="rights_end_at" defaultValue={utcInput(schedule.rights_end_at)} /></label>
      <SubmitButton>Save schedule</SubmitButton>
      {state.error && <p className="form-error" role="alert">{state.error}</p>}
      {state.success && <p className="form-success" role="status">{state.success}</p>}
    </form>
    <p className="field-hint">Immediate publish/unpublish remains in the header. Due schedules transition automatically when public catalog traffic is served; rights windows are enforced independently.</p>
  </section>;
}
