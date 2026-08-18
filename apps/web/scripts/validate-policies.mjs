import { readFileSync } from "node:fs";

const required = new Set(["privacy", "terms", "copyright-takedown", "cookies-analytics",
  "accessibility", "community-rules", "subscription-refunds", "data-requests"]);
const file = new URL("../content/policies.json", import.meta.url);
const value = JSON.parse(readFileSync(file, "utf8"));
if (value.package_version !== 1 || !Array.isArray(value.documents)) throw new Error("Policy package is invalid");
const slugs = new Set(value.documents.map((document) => document.slug));
if (slugs.size !== required.size || [...required].some((slug) => !slugs.has(slug))) throw new Error("Policy package does not contain the required document set");
if (process.env.POLICY_REQUIRE_APPROVED === "true") {
  for (const document of value.documents) {
    const text = JSON.stringify(document);
    if (document.status !== "approved" || !document.version || document.version.includes("DUMMY") ||
        !document.effective_at || !document.approved_by || !Array.isArray(document.sections) ||
        document.sections.length === 0 || text.includes("DUMMY") || text.includes("TODO")) {
      throw new Error(`Policy ${document.slug} is not approved production content`);
    }
    const bodyLength = document.sections.flatMap((section) => section.paragraphs ?? []).join(" ").trim().length;
    if (bodyLength < 200) throw new Error(`Policy ${document.slug} is too short for approved production content`);
  }
}
console.log(`policy validation: PASS (${value.documents.length} documents, approved required=${process.env.POLICY_REQUIRE_APPROVED === "true"})`);
