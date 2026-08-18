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

$manifestPath = Join-Path $packageRoot 'MANIFEST.sha256'
$manifest = Get-Content -LiteralPath $manifestPath
$manifestPaths = [System.Collections.Generic.HashSet[string]]::new(
  [System.StringComparer]::Ordinal
)
foreach ($line in $manifest) {
  if ($line -notmatch '^([A-F0-9]{64})  (.+)$') {
    $errors.Add("Malformed manifest row: $line")
    continue
  }
  $target = Join-Path $packageRoot $Matches[2]
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    $errors.Add("Manifest path missing: $($Matches[2])")
    continue
  }
  $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
  if ($actual -ne $Matches[1]) {
    $errors.Add("Manifest mismatch: $($Matches[2])")
  }
  if (-not $manifestPaths.Add($Matches[2])) {
    $errors.Add("Duplicate manifest path: $($Matches[2])")
  }
}

$expectedPaths = $packageFiles |
  Where-Object { $_.FullName -ne $manifestPath } |
  ForEach-Object {
    $_.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
  }
foreach ($path in $expectedPaths) {
  if (-not $manifestPaths.Contains($path)) {
    $errors.Add("Manifest omits package file: $path")
  }
}
foreach ($path in $manifestPaths) {
  if ($expectedPaths -notcontains $path) {
    $errors.Add("Manifest lists unexpected file: $path")
  }
}

if ($errors.Count) {
  $errors | ForEach-Object { Write-Error $_ }
  exit 1
}

Write-Output "PASS: $($skills.Count) installable game-development skills"
