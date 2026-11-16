# Foundry setup and provisioning (live mode)

> Live generation was verified on all five model variants on 2026-11-16 after administrator-led enablement
> and deployment. The steps below are a setup reference, not permission to register features or accept terms.
> Actual endpoint, tenant and subscription identifiers are kept out of this public repository.

## 0. Prerequisites and decisions (administrator)

- **Choose a designated non-production demo subscription and Foundry resource.** Don't use a production
  subscription.
- **Review the fal preview terms.** fal processes data outside Microsoft facilities, and Microsoft
  agreements/DPA/certifications do not apply (see [governance.md](governance.md)). Only after that review, register
  the preview feature:

```bash
az feature register --namespace Microsoft.CognitiveServices --name Fal.EnableDeploy
az feature show --namespace Microsoft.CognitiveServices --name Fal.EnableDeploy --query properties.state
az provider register --namespace Microsoft.CognitiveServices
```

## 1. Deploy the five models

Deploying requires the **Foundry Owner** role. Kling v3 Pro uses the **US Data Zone** offering; the LTX and
MiniMax models use **Global Standard (PayGo)**. Get exact model names from the catalog:

```bash
az cognitiveservices account list-models -g <rg> -n <resource> --query "[?format=='fal.ai'].{name:name,version:version}"
az cognitiveservices account deployment create -g <rg> -n <resource> \
  --deployment-name minimax-h3-max --model-name Fal-MiniMax-H3-Max --model-format fal.ai \
  --model-version <version> --sku-name GlobalStandard --sku-capacity 1
```

Repeat for the Turbo, LTX-2.5 Fast/Pro and Kling v3 Pro deployments, using the names and SKUs that `list-models`
returns (Kling uses the Data Zone SKU). Put the deployment names in the `FOUNDRY_DEPLOYMENT_*` variables.

**Rate limits (all five models):** the free tier gets 0 RPM, tiers 1–4 get 2 RPM, and tiers 5–7 get 40 RPM. At
2 RPM, the three parallel drafts may queue; keep the pre-cached fallbacks ready.

## 2. RBAC and auth

- Callers need **Cognitive Services User** (or Foundry User) on the resource.
- Auth uses scope `https://cognitiveservices.azure.com/.default`. Set `FOUNDRY_TENANT_ID`
  (fallback `AZURE_TENANT_ID`) to select `AzureCliCredential` without browser fallback.
  If the CLI default account is in another tenant, also set `FOUNDRY_SUBSCRIPTION_ID` to your demo subscription.
  This selects the account without changing the CLI default. Subscription selection takes precedence over
  tenant selection because Azure CLI rejects passing both selectors in one token request.
  The live extra requires `azure-identity>=1.20`, which introduced the subscription selector.
  With neither selector, the existing `DefaultAzureCredential` chain is used.
  `FOUNDRY_API_KEY` is an optional alternative only if local auth is enabled on the resource.
- **A fal.ai `FAL_KEY` is not used.** Existing fal.ai credentials and deployments can't be reused on Foundry.

## 3. Configure and verify

```powershell
pip install -e ".[live]"
copy .env.example .env   # SKU2SCENE_MODE=live, FOUNDRY_ENDPOINT, FOUNDRY_DEPLOYMENT_*
sku2scene readiness --check-auth            # read-only: token acquisition + free authorization probe
python scripts\precache.py                  # plan + cost only
python scripts\precache.py --yes            # billable: real renders, manifest provenance -> "foundry"
```

`precache.py` refuses to make billable calls without `--yes`. After a successful run, each manifest entry records
`provenance: "foundry"`, the deployment, the `request_id` and a timestamp.

Authentication is not authorization: readiness probes a fresh random nonexistent request ID on the Turbo status route,
without generating media. HTTP 404/422 (or 200) establishes access to that operation; HTTP 401/403 does not.
Assign **Foundry User** on the account and allow time for RBAC propagation before spending on generation.
Other errors (including 429) leave access unverified. This probe does not establish model quota, successful
generation, terms acceptance, or access to every deployment.
An exact URL queried before RBAC propagates can continue returning a cached denial. Use a fresh probe ID
rather than repeatedly polling the same nonexistent request. Real generation jobs already have unique IDs.
Status/result GETs also carry a unique query value: a first live smoke test recovered an accepted job from a
stale 401 by changing only that query. The client never resubmits a job just to recover polling.
An immediate status/result 401 after an accepted POST can also be transient. The client retries these free
GETs with fresh query values and backoff (3, 5, 7, 9, then 10 seconds) for up to three minutes per operation.
Persistent denial raises an explicit authorization error; retain the request ID for recovery, not resubmission.
The ledger/manifest records wall-clock latency, not fal's `timings.inference` value.

## 4. Optional live brand screening

The demo exercised a vision-capable Azure OpenAI deployment and Content Safety on the same authorized
Foundry account. For a new environment, an authorized administrator can deploy the tested vision model:

```bash
az cognitiveservices account deployment create -g <rg> -n <resource> \
  --deployment-name brand-qa-vision --model-name gpt-5.4-mini --model-version 2026-03-17 \
  --model-format OpenAI --sku-name DataZoneStandard --sku-capacity 50
```

Availability and quota are subscription/region dependent; this is not an instruction to provision automatically.
In ignored `.env`, set `AZURE_OPENAI_ENDPOINT=https://<resource>.cognitiveservices.azure.com`,
`AZURE_OPENAI_VISION_DEPLOYMENT=brand-qa-vision` and
`CONTENT_SAFETY_ENDPOINT=https://<resource>.cognitiveservices.azure.com`.
These requests reuse the shared Entra credential factory; no API key is needed when local auth is disabled.

`sku2scene qa --job <job-id> --sku NWC-LTO-PCB-16` screens real frames against the approved catalog reference.
Precache runs store portable screening evidence in the manifest, including measured scores, findings and
Content Safety severities. A pass sets `automated_checks_passed`, never human publication approval.
Vision and Content Safety calls incur their own charges, separate from video-generation estimates.

The client retries explicit HTTP 429 rejections up to three times, respecting numeric `Retry-After`
(up to 120 seconds per wait; otherwise 60 seconds). It never retries a paid submit on network errors or 5xx
responses, where acceptance is uncertain. Check the original request before manually retrying.

## Verified status and remaining prerequisites

All five model variants completed live smoke generation and returned downloaded MP4s using Entra authentication.
See [live-validation.md](live-validation.md) for measured wall times and the cache manifest for individual rendered-clip provenance.
This does not verify every supported mode, resolution, duration, region or deployment offering.

| Observation | Next owner |
| --- | --- |
| A fresh clone contains no endpoint, tenant, subscription or credentials | Presenter: supply your own authorized demo target in ignored `.env` |
| New subscriptions still require administrator review/registration of separate fal terms | Administrator |
| Vision scoring and Content Safety were exercised on authentic generated frames | Presenter: review the screening evidence and sign off manually before publication |
| Native audio was requested for Kling and an audio stream was verified | Presenter: listen for cue alignment; stream presence alone is not semantic audio QA |
