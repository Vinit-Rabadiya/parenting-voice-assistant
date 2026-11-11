# Containers and Azure hosting

[Documentation home](../README.md#documentation). Commands run from the repository root.
Review [deployment modes and provider requirements](deployment.md) before using
these hosting instructions. Hosting does not authorize real caregiver data.

## Local container verification

The container builds the web interface and serves it with the existing API on one
origin. `SERVE_FRONTEND=true` enables this layout; ordinary Vite development keeps
the existing routing. The image caches the current `base` speech model during the
build, uses one server worker, and runs as a non-root user. Backend credentials
are supplied only when the container runs. The four `VITE_FIREBASE_*` build values
are public browser configuration, not Firebase Admin credentials.

With Docker Desktop's Linux engine running and the existing `.env` and
`frontend/.env.local` configured, run from the repository root:

```powershell
docker compose --env-file .env --env-file frontend/.env.local up --build -d
docker compose --env-file .env --env-file frontend/.env.local ps
```

Open **http://localhost:8001**. Check sign-in, the child selector, typed guidance,
recording, playback and history. Compose binds only to `127.0.0.1`, mounts the
existing Firebase Admin key read-only, and uses development mode solely for this
local HTTP check. The image itself defaults to production validation. This local
Compose file must not be used as public hosting configuration.

Add `http://localhost:8001/*` to the Firebase browser key's allowed website
referrers in Google Cloud Console, keeping existing development entries and API
restrictions. Firebase Authentication's authorized domains must also include
`localhost`. The public HTML sends only its origin as a referrer so the browser-key
restriction can be checked; private API responses retain `no-referrer`.

Stop the local container when verification is finished:

```powershell
docker compose --env-file .env --env-file frontend/.env.local stop
```

The image forwards stop signals through a small init process. Compose allows up
to 60 seconds for shutdown and does not restart the container automatically.

These commands do not create Azure resources. The first build downloads runtime
packages and the speech model; subsequent builds reuse unchanged layers. Model
downloads are disabled at runtime for the cached model. Changing the container's
speech model requires including that model in a rebuilt image.

Local Linux verification on 1 November 2026 checked the webpage, built assets,
API health, unauthenticated private routes and credential-file exclusions. The
cached model loaded with networking disabled and processed a silent WAV. Observed
idle app memory was about 234 MiB; this is not a peak-load or speech-accuracy
benchmark. The Windows project checks passed with 1,176 backend tests, 234 UI tests and
seven audio tests, alongside lint and the frontend build.
Signed-in container checks also covered typed and recorded messages, transcript
editing, Listen/Stop, and reopening saved history after refresh. The public-page
referrer correction passed 22 focused hosting/security checks. Manual shutdown
completed with exit code zero and left the container stopped.

## Automatic deployment

The `Deploy Application` workflow publishes a container image after `CI Pipeline` passes
for a push to `main`. Pull requests do not publish or deploy images. The workflow
checks the exact commit again before deployment and skips superseded commits.
Image tags contain the commit SHA; Azure uses the immutable image digest. Docker
layers are cached to reuse unchanged dependencies and the speech model.

The initial deployment targets 3–5 testers on the Consumption plan. Start with a single
active revision and minimum/maximum replica counts of one while testing, then
explicitly stop the app after each session. This keeps the model loaded during a
session and limits normal autoscaling. Check simultaneous voice requests on the
host before changing capacity; the local idle-memory measurement is not a load
test.

Configure these under **Settings → Secrets and variables → Actions**:

| Type | Name | Purpose |
| --- | --- | --- |
| Variable | `DEPLOYMENT_AUTOMATION_ENABLED` | Set to `true` to enable image publishing. |
| Variables | `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` | Public Firebase browser configuration, matching the local frontend. |
| Variable | `AZURE_DEPLOY_ENABLED` | Set to `true` after the hosted configuration is verified. Until then, only image publishing is enabled. |
| Variables | `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINER_APP` | Names of the existing Azure resources. |
| Secrets | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | Azure deployment identity identifiers used by OpenID Connect. |

The workflow uses GitHub's temporary `GITHUB_TOKEN` to publish to the private
GitHub Container Registry. It does not need a personal upload token. Verify the
package remains private after the first publish. Azure downloads the private image
using a separate token with only `read:packages`, stored in the Container App's
registry secret. Renew that credential before it expires; publishing a new image
does not renew Azure's download credential.

Configure an Azure federated identity credential for
`repo:Vinit-Rabadiya/parenting-voice-assistant:ref:refs/heads/main`, with issuer
`https://token.actions.githubusercontent.com` and audience
`api://AzureADTokenExchange`. Grant that identity the Container Apps Contributor
role scoped to the existing Container App. The workflow updates that app; it does
not create a resource group, environment or registry. Runtime Gemini, Qdrant and
Firebase Admin credentials remain in Azure's runtime secret configuration.

After the Azure identity and `AZURE_DEPLOY_ENABLED` are configured, successful main
updates deploy automatically while the application is running. While
it is stopped, the image is published and the app stays stopped. When needed,
open **Actions → Deploy Application → Run workflow**, select **main**, and choose
**start**. This builds or reuses the latest checked main image, starts the app,
applies the image and checks HTTPS health. Choose **stop** when the application is no longer needed;
the workflow verifies the stopped state. **publish** builds the image without
changing Azure. These operations are serialized, so a Stop run can wait for an
existing workflow; the Azure portal's Stop control is also available.

Image publishing uses GitHub Actions minutes and cache storage. The hosted application
requires its HTTPS, host, proxy, provider terms and runtime secret configuration
to be completed before enabling Azure deployment. Existing production validation
still applies. Workflow validation alone does not verify a hosted deployment.

The v0.2.0 hosting record names `littlecare-app` in `parenting-voice-rg`, with
`littlecare-standard-env` in Switzerland North. That record describes image
publishing with Azure updates awaiting configuration. Current workflow variables,
running image, subscription state and provider confirmations were not checked in
this documentation update. Compare the actual deployed image digest with the
intended release; publishing a GitHub release does not itself update Azure.

## Custom domain hosting

Azure Container Apps Express does not support custom domains. The initial transfer
to Standard Consumption hosting is defined in
[`infra/azure-standard.json`](../infra/azure-standard.json). It creates
`littlecare-standard-env` and `littlecare-app` in Switzerland North, copies the
source app's image, startup command, environment variables, probes and scaling,
and reuses the existing logging workspace.
The environment explicitly selects `WorkloadProfiles` mode with only the `Consumption`
profile. Verify that mode and the environment's public IP before configuring DNS.
Azure resolves the existing app's credentials during deployment; no secret values
belong in the template, command arguments or deployment outputs. The host allowlist
is updated for `littlecare.app` and the replacement app's generated Azure hostname.

Preview the initial transfer without creating resources:

```powershell
az deployment group what-if --resource-group parenting-voice-rg --template-file infra/azure-standard.json --mode Incremental --result-format ResourceIdOnly
```

After reviewing the preview and Consumption costs, create the environment first:

```powershell
az deployment group create --resource-group parenting-voice-rg --name littlecare-standard-environment --template-file infra/azure-standard.json --parameters deployApplication=false --mode Incremental --query properties.outputs
```

Verify `WorkloadProfiles` mode and a nonempty public IP before copying the app:

```powershell
az deployment group create --resource-group parenting-voice-rg --name littlecare-standard-application --template-file infra/azure-standard.json --parameters deployApplication=true --mode Incremental --query properties.outputs
```

Use the existing deployment workflow for later image updates. Reapplying this initial
transfer would copy settings from the source again and can replace later configuration.
Keep `parenting-voice-app` stopped during the transfer and retain it until the replacement
has passed the signed-in workflow checks. Firebase and Qdrant data remain in their
existing services.

The deployment outputs provide the replacement URL, apex A-record address and the
public verification value for the `asuid` TXT record. Add those records at the domain
registrar, then bind the domain with Azure's free managed certificate. The application
must be running during certificate issuance and renewals. Add `littlecare.app` to
Firebase Authentication's authorized domains and the Firebase browser key's allowed
HTTPS website referrers before testing sign-in. Point the deployment workflow's app
variable and Azure role scope at the replacement only after it has been verified.

The 2 November 2026 hosting record uses **https://littlecare.app**, an apex A
record of `74.161.125.239`, an `asuid` ownership record and an Azure-managed
certificate. These are historical setup values; inspect the actual DNS and
certificate before reusing them. On 2 November 2026, HTTPS returned the frontend and its JavaScript,
`/api/health/live` returned 200, an unauthenticated `/api/me` returned 401, and
HTTP redirected to HTTPS. Google sign-in and the chat screen also passed a manual
check on this domain. This is a hosted smoke check, not a repeat of every workflow
acceptance scenario.

To operate the current app in the Azure portal:

1. Open **Container Apps → littlecare-app → Overview**.
2. Select **Start** before a session and wait for **Running** before opening the site.
3. Select **Stop** when finished and confirm the status becomes **Stopped**.

Keep `parenting-voice-app` stopped. Stopping compute does not remove stored data,
the domain or the certificate. Requests cannot reach a stopped app. Stored logs,
other services and domain renewal can still incur separate charges. The configured
budget sends alerts; it is not a spending cap. Certificate renewal requires the app
to be reachable, so check certificate validity before a session after a long shutdown.
