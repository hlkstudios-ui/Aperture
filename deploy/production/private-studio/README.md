# Private owner-only Studio gateway

This gateway is the only supported production entrance to Aperture Studio. The public
Hostinger application returns `404` for `/studio*` and `/admin*` unless the request
contains a high-entropy edge credential. The credential is injected by this loopback-only
gateway and is never sent to browser JavaScript.

The route name is not the security boundary. Tailscale device identity, the tailnet grant,
the loopback listener, the edge credential, the administrator session, and MFA are separate
boundaries. There is no claim of absolute security.

## Credential-last setup

1. Run the gateway on the Hostinger VPS or on a separate minimal Ubuntu LTS machine. Enable
   automatic security updates and configure the Hostinger managed firewall with **no public
   inbound rule for the gateway**. Do not expose 8080, PostgreSQL, Redis, MinIO, or ClamAV.
2. Install Docker from its signed upstream repository and install Tailscale. Create a tagged,
   reusable, short-lived Tailscale enrollment key. Run `tailscale up --auth-key=... --hostname
   aperture-studio-gateway --advertise-tags=tag:aperture-studio --ssh`, revoke/remove the key,
   and confirm the device is owned by the tag.
3. Copy `tailnet-policy.example.hujson` into the Tailscale policy editor, replace the dummy
   owner email, and validate that only that exact identity can reach TCP 443 or use checked SSH.
4. Fill the private-Studio section of the repository-root `.env`. The Compose gateway reads
   that same file. Use the exact same `ORIGIN_EDGE_SECRET` and `STUDIO_EDGE_SECRET` injected
   into the Hostinger application stack,
   while keeping those two values independent. Generate each with a password manager or
   `openssl rand -base64 48`; never place them in shell history, source control, logs, URLs,
   browser storage, or support messages. Set mode `0600`.
5. Start the loopback gateway with `docker compose up -d`. Confirm port 8080 is bound only to
   `127.0.0.1`.
6. Publish it only inside the tailnet:

   ```bash
   sudo tailscale serve --bg --https=443 http://127.0.0.1:8080
   ```

7. Put the resulting `https://aperture-studio-gateway.<tailnet>.ts.net` URL in
   `ADMIN_WEB_ORIGIN` and open `/studio/login` through that URL. Require administrator MFA.

## Required acceptance checks

- Public customer hostname `/studio`, `/studio/login`, and `/api/admin/auth/login` return 404.
- The direct Hostinger origin returns the same 404 responses.
- The tailnet hostname is unreachable from a device outside the tailnet.
- A tailnet member other than the exact owner identity is denied by policy.
- The approved owner device reaches Studio, signs in with MFA, uploads, processes, and signs out.
- Removing either edge secret or changing it on either side fails closed with 404.
- Revoke the gateway device and confirm access stops before considering deployment complete.

Keep the public Hostinger origin because it serves the customer website. The private edge
credential prevents direct-origin bypass; the loopback gateway itself has no public inbound
surface.
