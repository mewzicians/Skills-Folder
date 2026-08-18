param(
  [string]$Destination = $(if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME 'skills'
  } else {
    Join-Path $HOME '.codex\skills'
  })
)

$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceRoot = Join-Path $packageRoot 'skills'
$backupRoot = Join-Path $Destination (
  '.game-skill-suite-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
)

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$installed = @()

Get-ChildItem -LiteralPath $sourceRoot -Directory | Sort-Object Name |
  ForEach-Object {
    $target = Join-Path $Destination $_.Name
    if (Test-Path -LiteralPath $target) {
      New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
      Copy-Item -LiteralPath $target -Destination (
        Join-Path $backupRoot $_.Name
      ) -Recurse -Force
      Remove-Item -LiteralPath $target -Recurse -Force
    }
    Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
    $installed += $_.Name
  }

[pscustomobject]@{
  destination = $Destination
  backup = $(if (Test-Path -LiteralPath $backupRoot) {
    $backupRoot
  } else {
    $null
  })
  installed = $installed
} | ConvertTo-Json -Depth 4
