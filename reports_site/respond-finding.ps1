#Requires -Version 5.1
<#
.SYNOPSIS
    Posts a maintainer response to a diagnostics finding on the receiver API.

.DESCRIPTION
    Sends a PATCH to <endpoint>/api/v1/findings/<FindingId> with {response_md: Message}.
    Endpoint defaults to docs/automated-review/review-state.json diagnostics_scan.endpoint.
    Token defaults to $env:USERPROFILE\.bookbridge\diagnostics-read.key.

.PARAMETER FindingId
    Numeric finding id to respond to (required, positional).

.PARAMETER Message
    Response markdown text (required, positional). Must be non-empty and <=10000 chars.

.PARAMETER Endpoint
    Override the receiver base URL (for local testing / emergency use).

.PARAMETER TokenFile
    Override the token file path (for local testing / emergency use).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)]
    [int]$FindingId,

    [Parameter(Mandatory=$true, Position=1)]
    [string]$Message,

    [string]$Endpoint,
    [string]$TokenFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Resolve defaults from repo-root review-state.json (when no override) ----
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot  = Split-Path -Parent $scriptDir
$statePath = Join-Path (Join-Path (Join-Path $repoRoot 'docs') 'automated-review') 'review-state.json'

if (-not $Endpoint) {
    if (-not (Test-Path -LiteralPath $statePath)) {
        Write-Error "review-state.json not found at $statePath and no -Endpoint override supplied."
        exit 1
    }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $Endpoint = $state.diagnostics_scan.endpoint
    if (-not $Endpoint) {
        Write-Error "diagnostics_scan.endpoint is missing or empty in review-state.json."
        exit 1
    }
}

# --- Token resolution --------------------------------------------------------
if (-not $TokenFile) {
    $TokenFile = Join-Path (Join-Path $env:USERPROFILE '.bookbridge') 'diagnostics-read.key'
}

# --- Validate inputs ---------------------------------------------------------

# Message: trim, reject empty / overlong
$Message = $Message.Trim()
if ([string]::IsNullOrEmpty($Message)) {
    Write-Error "Message must not be empty."
    exit 1
}
if ($Message.Length -gt 10000) {
    Write-Error "Message exceeds 10000 characters ($($Message.Length))."
    exit 1
}

# Endpoint: must be absolute http/https
$Endpoint = $Endpoint.TrimEnd('/')
try {
    $uri = [System.Uri]$Endpoint
    if ($uri.Scheme -notin @('http', 'https')) {
        Write-Error "Endpoint must use http or https scheme, got '$($uri.Scheme)'."
        exit 1
    }
} catch {
    Write-Error "Endpoint '$Endpoint' is not a valid absolute URI."
    exit 1
}

# Token file: must exist and be non-empty
if (-not (Test-Path -LiteralPath $TokenFile)) {
    Write-Error "Token file not found: $TokenFile"
    exit 1
}
$token = (Get-Content -LiteralPath $TokenFile -Raw).Trim()
if ([string]::IsNullOrEmpty($token)) {
    Write-Error "Token file is empty: $TokenFile"
    exit 1
}

# --- Send PATCH --------------------------------------------------------------
$url = "$Endpoint/api/v1/findings/$FindingId"
$body = @{ response_md = $Message } | ConvertTo-Json -Depth 5

try {
    $null = Invoke-RestMethod `
        -Method Patch `
        -Uri $url `
        -Headers @{ Authorization = "Bearer $token" } `
        -ContentType 'application/json; charset=utf-8' `
        -Body $body `
        -TimeoutSec 30
} catch {
    $statusCode = $null
    try {
        $statusCode = [int]$_.Exception.Response.StatusCode
    } catch { }
    $statusText = if ($statusCode) { " (HTTP $statusCode)" } else { "" }
    Write-Error "Request failed$statusText : $($_.Exception.Message)"
    exit 1
}

Write-Host "Response saved for finding #$FindingId."
exit 0
