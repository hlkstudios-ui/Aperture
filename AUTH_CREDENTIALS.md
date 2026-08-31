# Authentication credentials

The sign-in screen is complete and runs locally in CAPTCHA test mode. OAuth buttons marked **Setup** remain intentionally disabled until both values for that provider are added to `.env`.

## Callback URLs

Use the website origin and same-origin gateway when registering callbacks:

- Google: `http://localhost:3000/api/gateway/auth/oauth/google/callback`
- Microsoft: `http://localhost:3000/api/gateway/auth/oauth/microsoft/callback`
- GitHub: `http://localhost:3000/api/gateway/auth/oauth/github/callback`
- Apple: `https://your-local-tls-host/api/gateway/auth/oauth/apple/callback`

Replace the example host with the storefront's public HTTPS origin when deploying. Apple uses
a cross-site form POST and therefore requires HTTPS during integration testing as well.

## Values to add to `.env`

```dotenv
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=

OAUTH_MICROSOFT_CLIENT_ID=
OAUTH_MICROSOFT_CLIENT_SECRET=

OAUTH_GITHUB_CLIENT_ID=
OAUTH_GITHUB_CLIENT_SECRET=

# Apple Services ID and generated client-secret JWT
OAUTH_APPLE_CLIENT_ID=
OAUTH_APPLE_CLIENT_SECRET=

# Cloudflare Turnstile
NEXT_PUBLIC_TURNSTILE_SITE_KEY=
TURNSTILE_SECRET_KEY=
CAPTCHA_REQUIRED=true
CAPTCHA_TEST_MODE=false
```

## Production checklist

1. Use separate OAuth applications and Turnstile widgets for staging and production.
2. Register the exact HTTPS callback URL for every provider.
3. Restrict the Turnstile widget to the deployed website hostname.
4. Set `CAPTCHA_TEST_MODE=false`; application startup rejects test mode when CAPTCHA is enabled outside development.
5. Keep all client secrets server-side. Only the Turnstile site key is intentionally public.
6. The Hostinger and DigitalOcean deployment validators reject one-sided OAuth pairs and
   reject CAPTCHA-enabled releases missing either Turnstile half. They also keep customer
   cookies host-only behind the same-origin gateway.
