"use server";

import { revalidatePath, updateTag } from "next/cache";

import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";

export type DomainActionState = {
  sequence: number;
  error: string;
  notice: string;
};

function value(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function nextState(previous: DomainActionState) {
  return previous.sequence + 1;
}

function actionError(previous: DomainActionState, error: unknown): DomainActionState {
  return {
    sequence: nextState(previous),
    error:
      error instanceof CatalogActionError
        ? error.detail
        : "The domain request could not be completed. Please try again.",
    notice: "",
  };
}

function refreshPage() {
  updateTag("site-domain");
  revalidatePath("/studio/domains");
}

export async function addDomainAction(
  previous: DomainActionState,
  form: FormData,
): Promise<DomainActionState> {
  const hostname = value(form, "hostname").toLocaleLowerCase().replace(/\.$/, "");
  if (
    !hostname
    || hostname.length > 253
    || /[\s/:@\\]/.test(hostname)
    || !hostname.includes(".")
  ) {
    return {
      sequence: nextState(previous),
      error: "Enter a domain name only, such as watch.example.com — without https, a path, or a port.",
      notice: "",
    };
  }

  try {
    await adminCatalogFetch("/admin/site/domains", {
      method: "POST",
      body: JSON.stringify({ hostname }),
    });
    refreshPage();
    return {
      sequence: nextState(previous),
      error: "",
      notice: `${hostname} was added. Publish the DNS records shown below, then check the connection.`,
    };
  } catch (error) {
    return actionError(previous, error);
  }
}

async function postDomainAction(
  previous: DomainActionState,
  form: FormData,
  operation: "refresh" | "make-primary",
): Promise<DomainActionState> {
  const id = value(form, "domain_id");
  const hostname = value(form, "hostname");
  const revision = Number(value(form, "revision"));
  if (!id || !hostname || !Number.isInteger(revision) || revision < 0) {
    return {
      sequence: nextState(previous),
      error: "The domain record is incomplete. Reload this page and try again.",
      notice: "",
    };
  }

  try {
    await adminCatalogFetch(`/admin/site/domains/${encodeURIComponent(id)}/${operation}`, {
      method: "POST",
      body: JSON.stringify({ revision }),
    });
    refreshPage();
    return {
      sequence: nextState(previous),
      error: "",
      notice:
        operation === "refresh"
          ? `Connection status refreshed for ${hostname}.`
          : `${hostname} is now the primary customer domain.`,
    };
  } catch (error) {
    return actionError(previous, error);
  }
}

export async function refreshDomainAction(
  previous: DomainActionState,
  form: FormData,
): Promise<DomainActionState> {
  return postDomainAction(previous, form, "refresh");
}

export async function makePrimaryDomainAction(
  previous: DomainActionState,
  form: FormData,
): Promise<DomainActionState> {
  return postDomainAction(previous, form, "make-primary");
}

export async function usePlatformDomainAction(
  previous: DomainActionState,
  form: FormData,
): Promise<DomainActionState> {
  const revision = Number(value(form, "revision"));
  const platformHostname = value(form, "platform_hostname");
  if (!platformHostname || !Number.isInteger(revision) || revision < 0) {
    return {
      sequence: nextState(previous),
      error: "The hosted-address record is incomplete. Reload this page and try again.",
      notice: "",
    };
  }

  try {
    await adminCatalogFetch("/admin/site/domains/use-platform", {
      method: "POST",
      body: JSON.stringify({ revision }),
    });
    refreshPage();
    return {
      sequence: nextState(previous),
      error: "",
      notice: `${platformHostname} is now the primary customer address. Connected custom domains remain available.`,
    };
  } catch (error) {
    return actionError(previous, error);
  }
}

export async function removeDomainAction(
  previous: DomainActionState,
  form: FormData,
): Promise<DomainActionState> {
  const id = value(form, "domain_id");
  const hostname = value(form, "hostname");
  const confirmation = value(form, "confirmation").toLocaleLowerCase().replace(/\.$/, "");
  const revision = Number(value(form, "revision"));
  if (!id || !hostname || !Number.isInteger(revision) || revision < 0) {
    return {
      sequence: nextState(previous),
      error: "The domain record is incomplete. Reload this page and try again.",
      notice: "",
    };
  }
  if (confirmation !== hostname.toLocaleLowerCase()) {
    return {
      sequence: nextState(previous),
      error: `Type ${hostname} exactly to confirm removal.`,
      notice: "",
    };
  }

  try {
    await adminCatalogFetch(`/admin/site/domains/${encodeURIComponent(id)}?revision=${revision}&confirmation=${encodeURIComponent(hostname)}`, {
      method: "DELETE",
    });
    refreshPage();
    return {
      sequence: nextState(previous),
      error: "",
      notice: `${hostname} was removed from this storefront.`,
    };
  } catch (error) {
    return actionError(previous, error);
  }
}
