$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Join-Path $packageRoot 'skills'
$forbidden = '(?i)' + ('office' + '\s*' + 'wars') + '|' +
  ('office' + 'wars') + '|' + ('offie' + '\s+' + 'war')
$errors = [System.Collections.Generic.List[string]]::new()
$gitRoot = Join-Path $packageRoot '.git'
$packageFiles = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force -File |
  Where-Object {
    -not $_.FullName.StartsWith(
      $gitRoot + '\',
      [System.StringComparison]::OrdinalIgnoreCase
    )
  }

$skills = Get-ChildItem -LiteralPath $skillRoot -Directory | Sort-Object Name
foreach ($skill in $skills) {
  $skillFile = Join-Path $skill.FullName 'SKILL.md'
  $agentFile = Join-Path $skill.FullName 'agents\openai.yaml'
  if (-not (Test-Path -LiteralPath $skillFile)) {
    $errors.Add("Missing SKILL.md: $($skill.Name)")
    continue
  }
  if (-not (Test-Path -LiteralPath $agentFile)) {
    $errors.Add("Missing agents/openai.yaml: $($skill.Name)")
  }
  $text = Get-Content -LiteralPath $skillFile -Raw
  if ($text -notmatch '(?s)^---\s+name:\s+[a-z0-9-]+\s+description:\s+.+?\s+---') {
    $errors.Add("Invalid frontmatter: $($skill.Name)")
  }
  $nameMatch = [regex]::Match($text, '(?m)^name:\s*([a-z0-9-]+)\s*$')
  if (-not $nameMatch.Success -or $nameMatch.Groups[1].Value -ne $skill.Name) {
    $errors.Add("Folder and frontmatter name differ: $($skill.Name)")
  }
  if (Test-Path -LiteralPath $agentFile) {
    $agentText = Get-Content -LiteralPath $agentFile -Raw
    $expectedPromptName = '$' + $skill.Name
    if ($agentText -notmatch [regex]::Escape($expectedPromptName)) {
      $errors.Add("Metadata prompt does not name $expectedPromptName")
    }
  }
}

$packageFiles | ForEach-Object {
    $match = Select-String -LiteralPath $_.FullName -Pattern $forbidden
    if ($match) {
      $errors.Add("Forbidden project reference: $($_.FullName)")
    }
  }


if ($errors.Count) {
  $errors | ForEach-Object { Write-Error $_ }
  exit 1
}

Write-Output "PASS: $($skills.Count) installable game-development skills"
