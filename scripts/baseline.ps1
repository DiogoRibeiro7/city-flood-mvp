param(
  [string]$ApiBase = "http://localhost:8000",
  [string]$WebBase = "http://localhost:5173",
  [int]$RequestCount = 30,
  [string]$OutFile = "docs/baselines/latest.md",
  [switch]$SkipCompose,
  [switch]$SkipSeed
)

$ErrorActionPreference = "Stop"

function Require-Docker {
  try {
    $null = docker version 2>$null
  } catch {
    Write-Error "Docker is not running or not reachable. Start Docker Desktop (Linux containers) and try again."
    exit 1
  }
}

function Percentile([double[]]$values, [double]$p) {
  if ($values.Count -eq 0) { return [double]::NaN }
  $sorted = $values | Sort-Object
  $idx = [math]::Ceiling($p * $sorted.Count) - 1
  if ($idx -lt 0) { $idx = 0 }
  if ($idx -ge $sorted.Count) { $idx = $sorted.Count - 1 }
  return [double]$sorted[$idx]
}

function Measure-Requests([string]$url, [int]$count) {
  $durations = New-Object System.Collections.Generic.List[double]
  for ($i = 0; $i -lt $count; $i++) {
    $ms = (Measure-Command { Invoke-WebRequest -UseBasicParsing -Uri $url }).TotalMilliseconds
    $durations.Add($ms)
  }
  $avg = ($durations | Measure-Object -Average).Average
  $min = ($durations | Measure-Object -Minimum).Minimum
  $max = ($durations | Measure-Object -Maximum).Maximum
  return [pscustomobject]@{
    Url = $url
    Count = $count
    AvgMs = [math]::Round($avg, 2)
    P50Ms = [math]::Round((Percentile $durations 0.50), 2)
    P95Ms = [math]::Round((Percentile $durations 0.95), 2)
    P99Ms = [math]::Round((Percentile $durations 0.99), 2)
    MinMs = [math]::Round($min, 2)
    MaxMs = [math]::Round($max, 2)
  }
}

Require-Docker

$composeSeconds = $null
if (-not $SkipCompose) {
  $composeSeconds = (Measure-Command { docker compose up -d --build }).TotalSeconds
}

if (-not $SkipSeed) {
  $seedSeconds = (Measure-Command {
    docker compose exec -T backend alembic upgrade head
    docker compose exec -T backend python -m floodmvp.jobs.seed_assets
    docker compose exec -T backend python -m floodmvp.jobs.seed_telemetry
    docker compose exec -T backend python -m floodmvp.jobs.run_analytics
  }).TotalSeconds
} else {
  $seedSeconds = $null
}

$health = Invoke-RestMethod -Uri "$ApiBase/v1/health"
if ($health.status -ne "ok") {
  throw "Health check failed: $($health | ConvertTo-Json -Compress)"
}

$cities = Invoke-RestMethod -Uri "$ApiBase/v1/cities"
if (-not $cities -or $cities.Count -eq 0) {
  throw "No cities returned from $ApiBase/v1/cities"
}
$cityId = $cities[0].city_id

$apiMetrics = @(
  Measure-Requests "$ApiBase/v1/health" $RequestCount,
  Measure-Requests "$ApiBase/v1/cities" $RequestCount,
  Measure-Requests "$ApiBase/v1/cities/$cityId/status" $RequestCount,
  Measure-Requests "$ApiBase/v1/events?city_id=$cityId&type=overflow&from=2024-01-01T00:00:00Z&to=2024-01-07T00:00:00Z" $RequestCount
)

$webMetrics = @(
  Measure-Requests "$WebBase/" $RequestCount
)

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
$lines = @()
$lines += "# Baseline results ($timestamp)"
$lines += ""
$lines += "## Stack"
if ($composeSeconds -ne $null) { $lines += "- compose_up_seconds: $([math]::Round($composeSeconds,2))" }
if ($seedSeconds -ne $null) { $lines += "- seed_all_seconds: $([math]::Round($seedSeconds,2))" }
$lines += ""
$lines += "## API"
foreach ($m in $apiMetrics) {
  $lines += "- $($m.Url)" 
  $lines += "  count=$($m.Count) avg_ms=$($m.AvgMs) p50_ms=$($m.P50Ms) p95_ms=$($m.P95Ms) p99_ms=$($m.P99Ms) min_ms=$($m.MinMs) max_ms=$($m.MaxMs)"
}
$lines += ""
$lines += "## Web"
foreach ($m in $webMetrics) {
  $lines += "- $($m.Url)" 
  $lines += "  count=$($m.Count) avg_ms=$($m.AvgMs) p50_ms=$($m.P50Ms) p95_ms=$($m.P95Ms) p99_ms=$($m.P99Ms) min_ms=$($m.MinMs) max_ms=$($m.MaxMs)"
}

$dir = Split-Path -Parent $OutFile
if ($dir -and -not (Test-Path $dir)) {
  New-Item -ItemType Directory -Path $dir | Out-Null
}
$lines -join "`n" | Set-Content -Path $OutFile

Write-Host "Baseline captured -> $OutFile"
