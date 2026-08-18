import policyPackage from "../../content/policies.json";

export type PolicyDocument = {
  slug: string;
  title: string;
  status: "approved" | "awaiting_owner_approval";
  version: string;
  effective_at: string | null;
  approved_by: string | null;
  sections: Array<{ heading: string; paragraphs: string[] }>;
};

const documents = policyPackage.documents as PolicyDocument[];

export function approvedPolicies(): PolicyDocument[] {
  return documents.filter((document) => document.status === "approved");
}

export function approvedPolicy(slug: string): PolicyDocument | undefined {
  return approvedPolicies().find((document) => document.slug === slug);
}
