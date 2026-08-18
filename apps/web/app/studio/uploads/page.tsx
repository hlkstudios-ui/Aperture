import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { UploadManager, type MediaAsset } from "./upload-manager";

export default async function UploadsPage() {
  const [admin, assets] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<MediaAsset[]>("/admin/uploads"),
  ]);
  return (
    <StudioShell admin={admin} active="uploads" eyebrow="Media intake" title="Source uploads">
      <p className="editor-intro">
        Video moves directly from this browser to private object storage. Studio records its
        identity and integrity metadata before transfer and verifies the stored object before
        completion.
      </p>
      <UploadManager initialAssets={assets} />
    </StudioShell>
  );
}
