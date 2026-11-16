# Foundry setup and provisioning (live mode)

> Nothing here has been run against a real subscription for this repo. These steps come from Microsoft Learn.
> Each one needs an owner with the right authority.

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
- Auth uses `DefaultAzureCredential` with scope `https://cognitiveservices.azure.com/.default` (`az login` locally,
  managed identity in CI). `FOUNDRY_API_KEY` is an optional alternative.
- **A fal.ai `FAL_KEY` is not used.** Existing fal.ai credentials and deployments can't be reused on Foundry.

## 3. Configure and verify

```powershell
pip install -e ".[live]"
copy .env.example .env   # SKU2SCENE_MODE=live, FOUNDRY_ENDPOINT, FOUNDRY_DEPLOYMENT_*
sku2scene readiness --check-auth            # read-only: env, deps, ffmpeg, token acquisition
python scripts\precache.py                  # plan + cost only
python scripts\precache.py --yes            # billable: real renders, manifest provenance -> "foundry"
```

`precache.py` refuses to make billable calls without `--yes`. After a successful run, each manifest entry records
`provenance: "foundry"`, the deployment, the `request_id` and a timestamp.

## Current blockers (as of this commit)

Live status: **no demo Foundry endpoint has been configured or verified for this repo.** A read-only check in
the build environment found the following. Other subscriptions or administrators may differ.

| Observation | Next owner |
| --- | --- |
| No `FOUNDRY_*` endpoint configuration present; the default CLI subscription was production-labelled | Presenter: designate a non-production demo target |
| `Fal.EnableDeploy` showed `NotRegistered` on the checked subscription | Administrator, after reviewing the fal terms |
| No fal deployments verified, so no live render exists; all `demo-cache/` clips are simulated | Presenter: deploy, then `precache.py --yes` |
| Optional: Azure OpenAI vision and Content Safety for measured QA | Presenter |
