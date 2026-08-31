export type ViewerAccessMode = "free" | "subscription_required";

export type MonetizationConnectionStatus =
  | "disabled"
  | "not_connected"
  | "onboarding_required"
  | "restricted"
  | "ready";

export type ViewerMonetizationRecord = {
  schema_version: 1;
  revision: number;
  access_mode: ViewerAccessMode;
  access_mode_change_available: false;
  provider: "disabled" | "stripe_connect";
  connection: MonetizationConnectionStatus;
  connected_account_id: string | null;
  livemode: boolean | null;
  details_submitted: boolean;
  charges_enabled: boolean;
  payouts_enabled: boolean;
  requirements_due: string[];
  active_plan_count: number;
  subscription_mode_eligible: boolean;
  updated_at: string | null;
  notice: string | null;
};

export type ViewerPlan = {
  id: string;
  code: string;
  name: string;
  description: string;
  price_cents: number;
  currency: string;
  interval: "month" | "year";
  max_streams: number;
  max_resolution: "720p" | "1080p" | "4K";
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export const defaultViewerMonetization: ViewerMonetizationRecord = {
  schema_version: 1,
  revision: 0,
  access_mode: "free",
  access_mode_change_available: false,
  provider: "disabled",
  connection: "disabled",
  connected_account_id: null,
  livemode: null,
  details_submitted: false,
  charges_enabled: false,
  payouts_enabled: false,
  requirements_due: [],
  active_plan_count: 0,
  subscription_mode_eligible: false,
  updated_at: null,
  notice: null,
};
