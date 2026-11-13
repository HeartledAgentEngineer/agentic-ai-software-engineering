# Foundry demos for typeFREE, readFREE, and ShotReader

This folder contains three local client/server demonstrations backed by a shared Azure core. They are evaluation examples, not production services or an enterprise rollout. The original personal-purpose applications remain separate: those use user-configured OpenRouter routes; these demos use Azure AI Speech (F0) for speech recognition/synthesis and Azure AI Vision (F0) for image OCR. Text cleanup defaults to GitHub Models (`gpt-4o-mini`); OpenRouter and Azure AI Foundry are optional alternatives configured in the core.

## Requirements and configuration

Use Python 3.12 on Windows for the microphone, hotkey, and audio clients. From the repository root, create an environment and install the demo dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tools/foundry-demos/shared_core/requirements_azure.txt -r tools/foundry-demos/requirements-dev.txt
```

Configure Azure Speech and Vision values in `tools/foundry-demos/shared_core/.env` (create this file yourself; it is not shipped):

```dotenv
AZURE_SPEECH_KEY=<your-speech-key>
AZURE_SPEECH_REGION=<your-speech-region>
AZURE_VISION_KEY=<your-vision-key>
AZURE_VISION_ENDPOINT=<your-vision-endpoint>
GITHUB_TOKEN=<your-github-models-token>
# Optional: set a random local client/server token in both terminals
PORTFOLIO_API_TOKEN=<your-local-demo-token>
```

The `.env` values above are placeholders. The code reads the Azure keys from this file; default text cleanup uses GitHub Models and requires `GITHUB_TOKEN`. Azure Speech and Vision also support `AZURE_AUTH_MODE=entra` through the Azure SDK's `DefaultAzureCredential` when the host already has a supported credential configured. This authenticates the demo's outbound Azure calls; it does not provide user SSO, caller identity validation, tenant roles, or a managed-identity deployment. You may instead set `LLM_PROVIDER=openrouter` with `OPENROUTER_API_KEY`, or `LLM_PROVIDER=azure_foundry` with the Foundry endpoint/deployment and the appropriate key or Entra sign-in. These are separate provider choices. Provider availability does not imply a free allowance, spending cap, privacy guarantee, or cost monitoring. Confirm current provider terms and limits before sending real data. Never commit credentials.

Azure resources and authentication must already exist. The bootstrap script provisions Azure resources and writes configuration, so it is deliberately not part of these setup commands. It has not been run as part of this demo verification.

## Run one demo

Run commands from the repository root in separate PowerShell terminals. Each server defaults to loopback (`127.0.0.1`); the optional `PORTFOLIO_API_TOKEN` must be set in both server and client environments if enabled. The server reads it from the shared-core `.env`; set the same value in the client terminal with `$env:PORTFOLIO_API_TOKEN = '<your-local-demo-token>'`. Keep the server bound to loopback for local evaluation. Do not expose it to the internet or deploy it as-is.

### typeFREE

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn TypeFree.server.main:app --app-dir tools/foundry-demos --port 8101
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe tools/foundry-demos/TypeFree/client/app.py
```

### readFREE

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn ReadFree.server.main:app --app-dir tools/foundry-demos --port 8102
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe tools/foundry-demos/ReadFree/client/app.py
```

### ShotReader

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn shotReader.server.main:app --app-dir tools/foundry-demos --port 8103
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe tools/foundry-demos/shotReader/client/app.py
```

The clients target their matching loopback ports by default. Speech/audio, image OCR, and configured LLM calls reach the selected cloud provider; local server binding does not make those calls offline. The optional bearer token is a demo client/server check, not SSO, tenant authorization, or a production security boundary.

## Shared core and offline checks

`shared_core/azure_free_core.py` centralizes Azure Speech, Azure Vision, authentication selection, and the optional text-cleanup providers. `shared_core/api_common.py` provides shared API authentication and health responses. The three server folders demonstrate separate service boundaries and are not a hardened deployment architecture.

From the repository root, enter `tools/foundry-demos` and run the offline source tests:

```powershell
Set-Location tools/foundry-demos
python -m pytest -q --disable-socket --allow-unix-socket --allow-hosts=localhost,127.0.0.1,::1 tests
```

These tests use fakes and do not require cloud calls. They do not verify real credentials, resource provisioning, live provider behavior, production cost controls, SSO, autoscaling, or deployment readiness.
