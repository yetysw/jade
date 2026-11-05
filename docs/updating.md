# Update jade

At the end of this page you know how jade finds and applies a new version.

jade checks the latest release of the Gitea repository set in `GITEA_API_URL` and `GITEA_REPO`. Each release carries the installer as an attachment (`Jade-Setup-x.y.z.exe` on Windows). The check is cached for one hour, never blocks the interface, and answers "up to date" when it cannot reach the server. For a private repository, set `GITEA_TOKEN` to a read token.

!!! note
    The default repository address is a placeholder on `example.com`. Without your own value, the check finds nothing. Turn it off with `UPDATE_ENABLED=0`.

## Workstations (`UPDATE_MODE=manual`)

An "Update available" button shows in the sidebar. Click it when you want: jade downloads the installer with a progress bar and starts it. The installer closes and restarts jade. To avoid the UAC prompt, install per user in `%LOCALAPPDATA%`.

## RDS servers (`UPDATE_MODE=scheduled`)

The button is hidden. A scheduled task runs as SYSTEM every day at 01:00 and applies the new version only if nobody is logged on, otherwise it waits for the next night. Register it once, as administrator:

```powershell
powershell -ExecutionPolicy Bypass -File installer\jade-update-task.ps1 -Register
```

The script also takes `-Force` (updates even with open sessions, which closes jade for those users), `-ApiUrl`, `-Repo`, `-Token`, `-SetupPassword`, `-Hour` and `-Minute`. Its log goes to `C:\ProgramData\Jade\logs`.

An update keeps your existing `backend\.env`.
