export type LegalPolicyRecord = {
  schema_version: 1;
  revision: number;
  status: "draft";
  legal_operator_name: string | null;
  country_code: string | null;
  region: string | null;
  support_email: string | null;
  privacy_email: string | null;
  copyright_email: string | null;
  minimum_user_age: number | null;
  governing_law_jurisdiction: string | null;
  updated_at: string | null;
};

export type LegalPolicyDraftInput = Pick<
  LegalPolicyRecord,
  | "legal_operator_name"
  | "country_code"
  | "region"
  | "support_email"
  | "privacy_email"
  | "copyright_email"
  | "minimum_user_age"
  | "governing_law_jurisdiction"
>;
