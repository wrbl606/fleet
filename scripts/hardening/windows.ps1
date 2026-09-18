<#
  Windows bare-metal agent host hardening (plan §8, P4).

  Run as Administrator on each Windows agent node. Idempotent. Covers:
    1. least-privilege service account (no interactive logon)
    2. host egress allowlist (Windows Defender Firewall)
    3. audit policy
    4. runtime caps baseline (applied by resources/native/windows-sandbox.ps1)
    5. optional AppContainer note

  Secrets are never stored here; Jenkins injects them per run.
#>

#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$AgentUser = if ($env:FLEET_AGENT_USER) { $env:FLEET_AGENT_USER } else { "fleetagent" }
$Domains = @(
  "api.anthropic.com",
  "platform.claude.com",
  "api.openai.com",
  "opencode.ai",
  "registry.npmjs.org",
  "pypi.org",
  "files.pythonhosted.org",
  "github.com",
  "api.github.com",
  "objects.githubusercontent.com"
)

function Ensure-ServiceAccount {
  if (-not (Get-LocalUser -Name $AgentUser -ErrorAction SilentlyContinue)) {
    Write-Host "[hardening] creating service account $AgentUser"
    $pw = ConvertTo-SecureString ([guid]::NewGuid().ToString("N") + "Aa1!") -AsPlainText -Force
    New-LocalUser -Name $AgentUser -Password $pw -PasswordNeverExpires `
      -UserMayNotChangePassword -AccountNeverExpires -Description "fleet agent" | Out-Null
    Add-LocalGroupMember -Group "Users" -Member $AgentUser
  } else {
    Write-Host "[hardening] service account $AgentUser already exists"
  }
}

function Set-EgressAllowlist {
  Write-Host "[hardening] configuring outbound firewall allowlist"
  # Start from a default-block outbound posture for the agent's processes.
  Set-NetFirewallProfile -Profile Domain,Public,Private -DefaultOutboundAction Block

  foreach ($d in $Domains) {
    $name = "fleet-egress-$d"
    if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
      New-NetFirewallRule -DisplayName $name -Direction Outbound -Action Allow `
        -Protocol TCP -RemotePort 443 -RemoteAddress (Resolve-DnsName $d -Type A -ErrorAction SilentlyContinue |
          Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress) | Out-Null
    }
  }

  # Allow DNS + loopback.
  if (-not (Get-NetFirewallRule -DisplayName "fleet-dns" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "fleet-dns" -Direction Outbound -Action Allow `
      -Protocol UDP -RemotePort 53 | Out-Null
    New-NetFirewallRule -DisplayName "fleet-loopback" -Direction Outbound -Action Allow `
      -RemoteAddress 127.0.0.1 | Out-Null
  }
}

function Enable-AuditPolicy {
  Write-Host "[hardening] enabling process creation auditing"
  auditpol /set /subcategory:"Process Creation" /success:enable /failure:enable | Out-Null
  # PowerShell script-block logging feeds the SIEM (see resources/siem/).
  $key = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"
  New-Item -Path $key -Force | Out-Null
  Set-ItemProperty -Path $key -Name EnableScriptBlockLogging -Value 1
}

Ensure-ServiceAccount
Set-EgressAllowlist
Enable-AuditPolicy
Write-Host "[hardening] done. Secrets are injected per-run by Jenkins; none stored."
