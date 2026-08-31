# Private owner-only Studio gateway

This gateway is the only supported production entrance to Aperture Studio. The public
Hostinger application returns `404` for `/studio*` and `/api/gateway/admin*` unless the request
contains a high-entropy edge credential. The credential is injected by this loopback-only
gateway and is never sent to browser JavaScript.

The gateway always forwards the canonical public application host and strips every optional
custom-domain identity header before adding its private Studio credentials. Customer-domain
routing therefore cannot change the owner-only Studio origin or enter the Studio trust boundary.

The route name is not the security boundary. Tailscale device identity, the tailnet grant,
the loopback listener, the edge credential, the administrator session, and MFA are separate
boundaries. There is no claim of absolute security.

## Credential-last setup

1. Run the gateway on the Hostinger VPS or on a separate minimal Ubuntu LTS machine. Enable
   automatic security updates and configure the Hostinger managed firewall with **no public
   inbound rule for the gateway**. Do not expose 8080, PostgreSQL, Redis, MinIO, or ClamAV.
2. Install Docker from its signed upstream repository and install Tailscale. Enroll the VPS as
   `aperture-origin` with a single-use, short-lived auth key, then revoke it and atomically clear
   `TAILSCALE_AUTH_KEY` from the owner `.env`. If a Tailscale API key was used for node or policy
   setup, revoke and clear that independently as well:

   ```bash
   python ../hostinger/prepare_vps_env.py clear-tailscale-auth-key --input ../../../.env
   python ../hostinger/prepare_vps_env.py clear-tailscale-api-key --input ../../../.env
   ```
3. Copy `tailnet-policy.example.hujson` into the Tailscale policy editor, replace the dummy
   owner email in the policy test, and validate the policy before saving it. Apply
   `tag:aperture-studio` to the VPS and disable node-key expiry for this unattended server.
   The owner retains normal access between personal devices. The tagged VPS accepts owner HTTPS
   on TCP 443 and accepts ordinary OpenSSH on TCP 22 only from the ephemeral `tag:aperture-ci`
   identity used by the protected GitHub deployment job. That CI identity is denied Studio HTTPS.
   Tailscale SSH remains disabled; deployment uses the VPS's normal OpenSSH daemon over the
   encrypted tailnet path with a dedicated, command-scoped deploy account.
4. Complete the approved-builder eight-image build/pin workflow in `../hostinger` first. Never
   render or deploy this gateway before `CADDY_IMAGE` has been resolved to the accepted immutable
   digest. Fill the private-Studio section of the same repository-root `.env`; Compose uses that
   file only as the owner source. Validate it and render a separate mode-0600 gateway artifact
   after the public runtime artifact. Both artifacts must select the same first-party Caddy
   digest. The gateway artifact contains
   `CADDY_IMAGE`, `PUBLIC_APP_ORIGIN`, `PUBLIC_APP_HOST`, `ORIGIN_EDGE_SECRET`, and
   `STUDIO_EDGE_SECRET`. The enrollment key and owner identity are never copied to the gateway:

   ```bash
   python validate_config.py --mode deploy --input ../../../.env
   python render_runtime.py --input ../../../.env --output runtime.local.env
   python ../hostinger/validate_caddy_coupling.py \
     --public-env ../../../.env --private-env runtime.local.env
   ```

   Transfer only `runtime.local.env` to the gateway through the encrypted administration
   channel and keep it mode 0600. Use the exact
   same edge secrets injected into the Hostinger application stack while keeping the two
   values independent. Generate each with a password manager or `openssl rand -base64 48`;
   never place them in shell history, source control, logs, URLs, browser storage, or support
   messages. Set mode `0600`.
5. From this directory on the gateway, start the loopback service from the sanitized artifact.
   Confirm port 8080 is bound only to `127.0.0.1`.

   ```bash
   docker compose --env-file runtime.local.env pull
   docker compose --env-file runtime.local.env up -d --no-build --wait --wait-timeout 120
   python ../hostinger/validate_caddy_coupling.py \
     --public-env ../../../.env --private-env runtime.local.env --check-running
   ```
6. Publish it only inside the tailnet:

   ```bash
   sudo tailscale serve --bg --https=443 http://127.0.0.1:8080
   ```

7. Put the resulting `https://aperture-origin.<tailnet>.ts.net` URL in
   `ADMIN_WEB_ORIGIN` and open `/studio/login` through that URL. Require administrator MFA.

## Required acceptance checks

- Public customer hostname `/studio`, `/studio/login`, `/api/gateway/admin/auth/login`, and
  legacy `/api/admin/auth/login` return 404.
- The direct Hostinger origin returns the same 404 responses.
- The tailnet hostname is unreachable from a device outside the tailnet.
- A tailnet member other than the exact owner identity is denied by policy.
- The approved owner device reaches Studio, signs in with MFA, uploads, processes, and signs out.
- Removing either edge secret or changing it on either side fails closed with 404.
- Revoke the gateway device and confirm access stops before considering deployment complete.

Keep the public Hostinger origin because it serves the customer website. The private edge
credential prevents direct-origin bypass; the loopback gateway itself has no public inbound
surface.

`CADDY_IMAGE` is one coupled release input even though two Compose projects consume it. Normal
release deployment must render both runtime artifacts from the same owner `.env` and redeploy both
projects. The Hostinger rollback controller synchronizes and verifies both projects automatically
when Caddy changes, including compensation to the pre-rollback digest after a failed target. Do not
call any release or rollback complete while this gateway runs a different digest from the public
edge. Retain the passing `validate_caddy_coupling.py --check-running` result with the evidence; a
mismatch exits nonzero without printing either image reference.
