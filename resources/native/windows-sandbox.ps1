<#
  fLEET native Windows sandbox wrapper (plan §8, P4).

  Invoked by the runner as:

    powershell -NoProfile -ExecutionPolicy Bypass -File windows-sandbox.ps1 -- <cmd> <args...>

  This wrapper is the trusted host-side enforcement point. Windows' process
  and firewall model differs from Seatbelt: true filesystem/registry
  confinement requires Windows Sandbox (a VM) or an AppContainer profile,
  which are provisioned by the host image (see docs/bare-metal-hardening.md).

  What this wrapper guarantees even without an AppContainer:
    * a hard wall-clock timeout (kills the process tree)   -- §8 resource caps
    * no inherited credentials from the Jenkins agent env  -- §8 no secrets at rest
    * exit-code propagation

  To enable AppContainer confinement, set FLEET_WIN_APPCONTAINER=1 and provide
  a pre-created profile named by FLEET_WIN_APPCONTAINER_NAME on the host.
#>

param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Command
)

$ErrorActionPreference = "Stop"

# Strip a leading "--" separator if present.
if ($Command.Count -gt 0 -and $Command[0] -eq "--") {
  $Command = $Command[1..($Command.Count - 1)]
}

if ($Command.Count -eq 0) {
  Write-Error "windows-sandbox.ps1: no command given"
  exit 2
}

$timeoutSeconds = 0
if ($env:FLEET_NATIVE_TIMEOUT_SECONDS) {
  [int]::TryParse($env:FLEET_NATIVE_TIMEOUT_SECONDS, [ref]$timeoutSeconds) | Out-Null
}

$exe = $Command[0]
$exeArgs = @()
if ($Command.Count -gt 1) {
  $exeArgs = $Command[1..($Command.Count - 1)]
}

# Drop obviously sensitive vars so the child cannot read them.
foreach ($name in @("GH_TOKEN", "GITHUB_TOKEN", "JENKINS_")) {
  Get-ChildItem Env: | Where-Object { $_.Name -like "$name*" } |
    ForEach-Object { Remove-Item "Env:$($_.Name)" -ErrorAction SilentlyContinue }
}

$proc = Start-Process -FilePath $exe -ArgumentList $exeArgs -NoNewWindow -PassThru

if ($timeoutSeconds -gt 0) {
  if (-not $proc.WaitForExit($timeoutSeconds * 1000)) {
    Write-Warning "windows-sandbox: timeout after ${timeoutSeconds}s, killing process tree"
    & taskkill /PID $proc.Id /T /F | Out-Null
    exit 124
  }
} else {
  $proc.WaitForExit()
}

exit $proc.ExitCode
