# Free-tier public staging

This target publishes a low-traffic demonstration without changing or weakening the Hostinger VPS production target. It is **staging only** and cannot satisfy the production launch gate.

## Topology

- Render Free web service: Next.js application.
- Render Free web service: FastAPI plus co-located media and scene workers.
- Supabase Free: PostgreSQL through the TLS pooled endpoint.
- Upstash-compatible free tier: TLS Redis.
- Cloudflare R2 free tier: private, S3-compatible demo media storage.
- Sentry developer/free project and a free SMTP provider.

Free worker instances are not available in the selected compute tier. `start_api.py` therefore supervises the API and both workers in one disposable container. If any child exits, the container exits so the platform restarts the whole unit. This deliberately differs from production's independent worker supervision.

## Owner setup

1. Create the free provider accounts. Provider credentials still belong to the owner and must never be committed.
2. Copy `credentials.example.env` to the ignored `credentials.local.env` and replace every `DUMMY_*` label.
3. Create a private R2 bucket. Configure browser CORS for the exact `STAGING_WEB_ORIGIN`; do not enable anonymous listing or reads.
4. Use Supabase's pooled TLS URL and a TLS `rediss://` URL. Run no production data through either service.
5. Validate inputs locally:

   ```sh
   python deploy/staging/free-tier/validate_config.py --mode deploy
   ```

6. Connect the repository to Render and create a Blueprint from `deploy/staging/free-tier/render.yaml`. Copy the corresponding values into each `sync: false` field. For web fields, set `API_ORIGIN`, `NEXT_PUBLIC_API_ORIGIN`, and `NEXT_PUBLIC_MEDIA_ORIGIN` to the API URL; set `NEXT_PUBLIC_OBJECT_STORAGE_ORIGIN` to the R2 S3 endpoint.
7. Keep automatic deployment disabled. Deploy the API first, then the web service, and confirm `/ready` before loading the web URL.
8. Provision the single staging administrator interactively through an approved one-off local command pointed at the staging database; enroll MFA immediately. Never place an administrator password in Render environment variables.
9. Upload only generated, owned, or verified public-domain clips small enough for the 50 MiB staging cap.

## Verification and limits

Run the normal public-edge and browser acceptance against the assigned origins. Record results as staging evidence only.

- Both Render services sleep after inactivity; first requests can take about a minute.
- API and workers stop together while sleeping, so queued media waits for an API wake-up.
- Two services share the provider's monthly free-instance allocation and can be suspended at quota.
- The 512 MiB class is suitable only for short, low-resolution demo clips; FFmpeg can exhaust it.
- Supabase free projects may pause after inactivity and have no production SLA.
- R2 free capacity is small relative to a movie catalog.
- No Toronto placement, HA, production backup/RPO/RTO, independent workers, private network, capacity guarantee, or production rollback evidence is claimed.
- Free hosting does not provide content licenses, territorial rights, approved policies, owner identity, or legal authorization.

The authoritative production path is `deploy/production/hostinger`.
