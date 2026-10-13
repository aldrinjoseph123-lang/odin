# Azure AD App Registration — Outlook, Teams, OneDrive

One Azure AD app registration powers all three integrations. Once it's registered, an admin clicks **Connect Microsoft 365** in Settings, signs in on Microsoft's real login page, and consents — no IDs to hunt down in Graph Explorer, no env vars for the sender mailbox or Teams channel. This is a one-time setup by whoever has access to Azure AD; the actual "grant access" step happens in the app itself.

## 1. Create the app registration

1. Go to [portal.azure.com](https://portal.azure.com) → **Azure Active Directory** → **App registrations** → **New registration**.
2. Name: `PMS Integration` (or anything).
3. Supported account types: **Accounts in this organizational directory only** (single tenant).
4. **Redirect URI** — this is required now (it wasn't in an earlier version of this doc): platform **Web**, URI `https://your-domain/integrations/callback` (or `http://127.0.0.1:5050/integrations/callback` while testing locally — Azure allows `http://localhost`/`127.0.0.1` redirect URIs for dev).
5. Click **Register**.

## 2. Note the IDs

On the app's **Overview** page, copy:
- **Application (client) ID** → `MS_CLIENT_ID`
- **Directory (tenant) ID** → `MS_TENANT_ID`

## 3. Create a client secret

1. **Certificates & secrets** → **New client secret**.
2. Any description, expiry per your policy (secrets expire — put a reminder on your calendar; when it expires, everyone has to reconnect).
3. Copy the **Value** immediately — it's only shown once. This is `MS_CLIENT_SECRET`.

## 4. Add API permissions (Delegated, not Application)

**API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions** → add:

- `Mail.Send`
- `Files.ReadWrite`
- `ChannelMessage.Send`
- `Team.ReadBasic.All`
- `Channel.ReadBasic.All`
- `Sites.ReadWrite.All` (backups into a SharePoint site)
- `Chat.Create`, `ChatMessage.Send`, `User.ReadBasic.All` (13 Oct 2026: each notification also as a direct Teams chat to the person it is for; `User.ReadBasic.All` finds a colleague by their email address)
- `offline_access` (usually pre-added — this is what lets the app refresh tokens for background jobs without you re-logging-in constantly)
- `User.Read` (usually pre-added)

You do **not** need to click "Grant admin consent" here — that consent happens automatically in the popup when an admin clicks Connect, as long as they have sufficient privilege (Global Administrator or Application Administrator) to consent on behalf of the organization for these permissions. If your tenant requires consent to be pre-granted centrally, an admin can still click **Grant admin consent for `<org>`** on this page instead — either path works.

## 5. Set environment variables

Wherever you run the app (shell, systemd unit, `.env` file, hosting platform's env var settings):

```bash
export MS_CLIENT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export MS_CLIENT_SECRET="the-secret-value-from-step-3"
export MS_TENANT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

That's it — no `MS_SENDER_UPN`, `MS_TEAM_ID`, or `MS_CHANNEL_ID` env vars anymore. Those are set by clicking through the app instead. Never commit these three to source control.

## 6. Connect in the app

1. Log in as an Admin user.
2. **Settings** → you'll see a **Connect Microsoft 365** button once the env vars above are set.
3. Click it → redirected to Microsoft's real sign-in page → sign in with an admin account → consent screen appears (with an "consent on behalf of your organization" checkbox if the account is an admin) → redirected back.
4. Settings now shows "Connected as you@yourcompany.com" — mail and OneDrive work immediately from this identity.
5. Pick a **Team** then a **Channel** from the dropdowns (populated live from your actual joined Teams — no manual IDs) and click **Save Channel**.
6. Check the boxes for which notifications/mirroring/backup you want, then **Send Test Email** / **Send Test Teams Message** to confirm before relying on it.
7. **Teams messages to people** (Settings › Notifications › Channels): every notification also goes to each staff member as a one-to-one Teams chat from the connected account, alongside the email. Partners and customers get email only (they sit in other tenants). Adding these permissions to an existing connection needs a **reconnect** (Disconnect, then Connect) so Microsoft asks for the new consent.
8. **Send email as** (Settings › Notifications): an alias of the connected mailbox to put in the From line, e.g. when the mailbox is shared with other systems. Needs `Set-OrganizationConfig -SendFromAliasEnabled $true` in Exchange Online; if Microsoft refuses the alias, Odin sends from the mailbox and tells the admins.
9. Each user (including you) still needs to set their own email on the **Account** page — that's who real-time project notifications get addressed to. The Microsoft 365 connection is just the "postman"; individual notification routing still uses each user's email field.

## 7. Schedule the recurring jobs (optional)

Real-time events fire automatically. The daily digest and the backups run from the scheduler (`scheduler` service in docker compose, or `python scheduler.py --once` from cron every few minutes) at the times set in **Settings → Notifications** and **Settings → Backups**. Backups to a SharePoint site need the `Sites.ReadWrite.All` delegated permission added to this registration; after adding it, **Disconnect** and **Connect Microsoft 365** again once so the token carries it.

Both respect the Settings toggles and the stored connection — they use the same refresh token as the interactive app, refreshing it automatically. If the connection is ever disconnected or the refresh token is revoked, both scripts just fail gracefully and log why; reconnect in Settings to fix.

## Sign in with Microsoft (staff) — a second, separate registration

Staff sign-in uses its **own** app registration, so signing in can never touch the mailbox connection above.

1. **App registrations** → **New registration**. Name: `Odin sign-in`. Supported account types: **Accounts in this organizational directory only**.
2. **Redirect URI**: platform **Web**, the exact address shown in Odin under **Settings → Sign-in & security → Microsoft sign-in** (it is built from **Settings → General → Public web address**, e.g. `https://odin.example.com/auth/microsoft/callback`).
3. **Certificates & secrets** → **New client secret**; copy the value.
4. No API permissions are needed beyond the default `User.Read`; Odin asks only for `openid profile email`.
5. Optional but recommended: **Enterprise applications** → *Odin sign-in* → **Properties** → **Assignment required = Yes**, then assign the staff (or a group) who may use Odin.
6. In Odin: paste the client ID, tenant ID and secret, **Save**, then **Try Microsoft sign-in**.
7. When it works, tick **Staff must sign in with Microsoft**. The password form disappears; accounts ticked **Password** on the Users page keep an emergency form at `/login/password` (every use is audited and the admins are notified). Odin refuses the switch until at least one active admin keeps a password.

First sign-ins by colleagues Odin doesn't know yet wait on the **Users** page for an admin to approve them with a role. Existing users are linked by their work email the first time they sign in with Microsoft; after that the Entra object ID is what binds them.

## Troubleshooting

- **AADSTS900023 "tenant identifier is neither a valid DNS name..."** — `MS_TENANT_ID` is wrong or a placeholder; use the real Directory (tenant) ID from step 2.
- **AADSTS50011 "redirect URI mismatch"** — the URI you're running the app on doesn't exactly match what's registered in step 1 (scheme, host, port, and path all have to match, including trailing slash).
- **"Sign-in session expired or mismatched"** — the CSRF `state` check failed, usually because you sat on the Microsoft login page too long or opened Connect in two tabs. Click Connect again.
- **Consent screen doesn't show the "on behalf of organization" checkbox** — the signed-in account isn't an admin in this tenant, or the permissions don't require admin consent in your tenant's policy; a non-admin can still connect for themselves, just without the org-wide grant.
- **Token refresh failing after it worked before** — the client secret expired (see step 3) or the refresh token was revoked (password reset, conditional access policy, etc.) — reconnect in Settings.
- **OneDrive upload 404** — the connected user's OneDrive may not be provisioned yet; visit `onedrive.com` once as that user to trigger provisioning, then retry.
