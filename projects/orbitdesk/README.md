# OrbitDesk

OrbitDesk is a Windows tray application whose best-established role is showing Claude Code and Codex quota and limit status. Per-topic role profiles and handover workflows are present in the code, but remain experimental; they are not a production-proven agent orchestration service.

## What is available

- **Quota and limit display — used day to day.** The tray and overview show measured Claude Code and Codex usage windows, reset information, and unknown or stale readings. The warning threshold is configurable. Claude refresh calls its OAuth usage endpoint; Codex status is read from local session data and can be actively refreshed through the Codex app server. A local interface does not mean offline operation.
- **Per-topic profiles — implemented, experimental.** A profile can store the expected master, worker provider, and model. These are routing preferences: saving a profile does not start a session or launch a worker process.
- **Handover workflow — implemented, experimental.** The code can create a technical handover package and process a target acknowledgement under local topic locks. The package contains technical metadata rather than project file contents. End-to-end operation across different agent products has not been established as a production service.
- **Automatic quota switch — optional, experimental.** The code contains a guarded Claude-to-Codex path. It is disabled by default and depends on fresh, valid measurements, configured topic pairs, ownership state, and acknowledgement handling.

## Scope and limits

OrbitDesk is a single-user Windows desktop application with state under `%USERPROFILE%/.master-schalter`. It is not a hosted team service and does not provide organization-wide SSO, multi-tenant authorization, central monitoring, or cost allocation. Local profiles and file locks do not replace company identity or access controls.

The app uses provider sign-in data already available to the user; it does not include a corporate secrets manager. Claude quota refresh sends an authenticated request to the Claude usage endpoint, so the app is not an offline monitor. Do not put credentials in the repository or in handover notes.

## Install and run

Requires Windows and Python 3.12 or newer. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[leiste,dev]"
.\.venv\Scripts\pythonw.exe -m master_schalter.leiste
```

The command-line entry points include `masterwechsel status` and `masterwechsel profil <topic> --json`. Profile selection reports stored configuration; it does not start an agent session.

## Verification

The public repository CI configures an OrbitDesk Windows test job. It installs the package with its UI and development extras and runs `python -m pytest -q`; the repository-wide workflow also has Gitleaks and Ruff jobs. This is automated verification of the code, not proof of a production multi-agent deployment. See the [public CI workflow](../../.github/workflows/ci.yml).

For the distinction between the personal desktop application, current checks, and an enterprise design proposal, see the [enterprise rollout guide](../../docs/enterprise-rollout.md).

The package metadata currently identifies version 0.5.1 and package name `master-schalter`; the Python modules and command names retain that name.
