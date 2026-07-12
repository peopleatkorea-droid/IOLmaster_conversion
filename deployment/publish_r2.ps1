param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")]
  [string]$Version,
  [string]$EnvFile = ".env.r2.local",
  [string]$Bucket = "",
  [string]$AccountId = "",
  [string]$AccessKeyId = "",
  [string]$SecretAccessKey = "",
  [string]$PublicBaseUrl = "",
  [string]$Prefix = "",
  [string]$ToolBasePath = "/tools/biometry-ood",
  [switch]$Promote,
  [switch]$SkipTests,
  [switch]$AllowDirtySource,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$PublishRoot = Join-Path $RepositoryRoot "dist\r2-publish"
$ReleaseRoot = Join-Path $PublishRoot ("releases\" + $Version)
$CurrentRoot = Join-Path $PublishRoot "current"

function Import-EnvFile([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) { return }
  $resolvedPath = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $RepositoryRoot $Path }
  if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) { return }
  foreach ($rawLine in Get-Content -LiteralPath $resolvedPath -Encoding UTF8) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#")) { continue }
    $parts = $line -split "=", 2
    if ($parts.Length -ne 2) { continue }
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
  }
}

function Resolve-Setting([string]$ParameterValue, [string]$EnvironmentName, [string]$Fallback = "") {
  if (-not [string]::IsNullOrWhiteSpace($ParameterValue)) { return $ParameterValue.Trim() }
  $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentName, "Process")
  if (-not [string]::IsNullOrWhiteSpace($environmentValue)) { return $environmentValue.Trim() }
  return $Fallback
}

function Require-Value([string]$Name, [string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value)) { throw "$Name is required." }
}

function Assert-PathInside([string]$Parent, [string]$Child) {
  $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
  $childFull = [System.IO.Path]::GetFullPath($Child)
  if (-not $childFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing filesystem operation outside $parentFull`: $childFull"
  }
}

function Resolve-PythonExecutable {
  $venvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPython -PathType Leaf) { return $venvPython }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return $python.Source }
  throw "Python was not found. Install Python or create .venv before publishing."
}

function Convert-ToHex([byte[]]$Bytes) {
  $builder = [System.Text.StringBuilder]::new($Bytes.Length * 2)
  foreach ($byte in $Bytes) { [void]$builder.AppendFormat("{0:x2}", $byte) }
  return $builder.ToString()
}

function Get-Sha256Hex([byte[]]$Bytes) {
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try { return Convert-ToHex $sha.ComputeHash($Bytes) } finally { $sha.Dispose() }
}

function Get-HmacSha256([byte[]]$Key, [string]$Value) {
  $hmac = [System.Security.Cryptography.HMACSHA256]::new($Key)
  try { return $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Value)) } finally { $hmac.Dispose() }
}

function ConvertTo-S3UriPath([string]$BucketName, [string]$ObjectKey) {
  $segments = @($BucketName) + ($ObjectKey -split "/")
  $encodedSegments = foreach ($segment in $segments) { [System.Uri]::EscapeDataString($segment) }
  return "/" + ($encodedSegments -join "/")
}

function Join-S3Key([string[]]$Parts) {
  return (($Parts | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "/").Replace("\", "/").Trim("/")
}

function Get-RelativePathCompat([string]$RootPath, [string]$ChildPath) {
  $rootFull = [System.IO.Path]::GetFullPath($RootPath).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
  $childFull = [System.IO.Path]::GetFullPath($ChildPath)
  $rootUri = [System.Uri]::new($rootFull)
  $childUri = [System.Uri]::new($childFull)
  return [System.Uri]::UnescapeDataString($rootUri.MakeRelativeUri($childUri).ToString()).Replace("\", "/")
}

function Get-ContentType([string]$Path) {
  switch ([System.IO.Path]::GetExtension($Path).ToLowerInvariant()) {
    ".html" { return "text/html; charset=utf-8" }
    ".css" { return "text/css; charset=utf-8" }
    ".js" { return "text/javascript; charset=utf-8" }
    ".json" { return "application/json; charset=utf-8" }
    default { return "application/octet-stream" }
  }
}

function Invoke-R2PutObject(
  [string]$ObjectKey,
  [string]$Path,
  [string]$ContentType,
  [string]$CacheControl
) {
  $endpointHost = "$AccountId.r2.cloudflarestorage.com"
  $uriPath = ConvertTo-S3UriPath $Bucket $ObjectKey
  $uri = "https://$endpointHost$uriPath"
  $service = "s3"
  $region = "auto"
  $now = (Get-Date).ToUniversalTime()
  $amzDate = $now.ToString("yyyyMMddTHHmmssZ", [Globalization.CultureInfo]::InvariantCulture)
  $dateStamp = $now.ToString("yyyyMMdd", [Globalization.CultureInfo]::InvariantCulture)
  $body = [System.IO.File]::ReadAllBytes($Path)
  $payloadHash = Get-Sha256Hex $body
  $canonicalHeaders = "cache-control:$CacheControl`ncontent-type:$ContentType`nhost:$endpointHost`nx-amz-content-sha256:$payloadHash`nx-amz-date:$amzDate`n"
  $signedHeaders = "cache-control;content-type;host;x-amz-content-sha256;x-amz-date"
  $canonicalRequest = "PUT`n$uriPath`n`n$canonicalHeaders`n$signedHeaders`n$payloadHash"
  $credentialScope = "$dateStamp/$region/$service/aws4_request"
  $requestHash = Get-Sha256Hex ([System.Text.Encoding]::UTF8.GetBytes($canonicalRequest))
  $stringToSign = "AWS4-HMAC-SHA256`n$amzDate`n$credentialScope`n$requestHash"
  $dateKey = Get-HmacSha256 ([System.Text.Encoding]::UTF8.GetBytes("AWS4$SecretAccessKey")) $dateStamp
  $dateRegionKey = Get-HmacSha256 $dateKey $region
  $dateRegionServiceKey = Get-HmacSha256 $dateRegionKey $service
  $signingKey = Get-HmacSha256 $dateRegionServiceKey "aws4_request"
  $signature = Convert-ToHex (Get-HmacSha256 $signingKey $stringToSign)
  $authorization = "AWS4-HMAC-SHA256 Credential=$AccessKeyId/$credentialScope, SignedHeaders=$signedHeaders, Signature=$signature"

  if ($DryRun) {
    Write-Host "[dry-run] upload $Path -> $ObjectKey ($CacheControl)"
    return
  }

  $client = [System.Net.Http.HttpClient]::new()
  $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Put, $uri)
  $content = [System.Net.Http.ByteArrayContent]::new($body)
  $response = $null
  try {
    $content.Headers.TryAddWithoutValidation("Content-Type", $ContentType) | Out-Null
    $request.Content = $content
    $request.Headers.TryAddWithoutValidation("Authorization", $authorization) | Out-Null
    $request.Headers.TryAddWithoutValidation("x-amz-content-sha256", $payloadHash) | Out-Null
    $request.Headers.TryAddWithoutValidation("x-amz-date", $amzDate) | Out-Null
    $request.Headers.TryAddWithoutValidation("Cache-Control", $CacheControl) | Out-Null
    $response = $client.SendAsync($request).GetAwaiter().GetResult()
    if (-not $response.IsSuccessStatusCode) {
      $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
      throw "R2 upload failed for $ObjectKey`: HTTP $([int]$response.StatusCode) $($response.ReasonPhrase) $responseBody"
    }
  } finally {
    if ($null -ne $response) { $response.Dispose() }
    $content.Dispose()
    $request.Dispose()
    $client.Dispose()
  }
  Write-Host "uploaded: $($PublicBaseUrl.TrimEnd('/'))/$ObjectKey"
}

function Write-JsonFile([string]$Path, [object]$Value) {
  $json = $Value | ConvertTo-Json -Depth 8
  [System.IO.File]::WriteAllText($Path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

function Invoke-RemoteReleaseCheck([string]$ExpectedVersion) {
  if ($DryRun) { return }
  $manifestUrl = "$($PublicBaseUrl.TrimEnd('/'))/$(Join-S3Key @($Prefix, 'releases', $ExpectedVersion, 'manifest.json'))?verify=$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
  $manifest = Invoke-RestMethod -Uri $manifestUrl -Method Get -Headers @{ "Cache-Control" = "no-cache" }
  if ([string]$manifest.version -ne $ExpectedVersion) {
    throw "Published manifest verification failed at $manifestUrl"
  }
  Write-Host "verified: $manifestUrl"
}

function Test-RemoteReleaseExists([object]$LocalManifest) {
  if ($DryRun) { return $false }
  $manifestUrl = "$($PublicBaseUrl.TrimEnd('/'))/$(Join-S3Key @($Prefix, 'releases', $Version, 'manifest.json'))?collision-check=$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
  $client = [System.Net.Http.HttpClient]::new()
  $response = $null
  try {
    $response = $client.GetAsync($manifestUrl).GetAwaiter().GetResult()
    if ([int]$response.StatusCode -eq 404) { return $false }
    if (-not $response.IsSuccessStatusCode) {
      throw "Could not check existing release manifest: HTTP $([int]$response.StatusCode) $($response.ReasonPhrase)"
    }
    $remoteJson = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $remoteManifest = $remoteJson | ConvertFrom-Json
    $localFiles = @($LocalManifest.files | ForEach-Object { "$($_.path):$($_.sha256)" }) -join "|"
    $remoteFiles = @($remoteManifest.files | ForEach-Object { "$($_.path):$($_.sha256)" }) -join "|"
    if ([string]$remoteManifest.version -ne $Version -or $remoteFiles -ne $localFiles) {
      throw "Release $Version already exists with different file hashes. Publish a new version instead of overwriting it."
    }
    Write-Host "release already exists with matching hashes: $Version"
    return $true
  } finally {
    if ($null -ne $response) { $response.Dispose() }
    $client.Dispose()
  }
}

Import-EnvFile $EnvFile
$Bucket = Resolve-Setting $Bucket "R2_BUCKET"
$AccountId = Resolve-Setting $AccountId "R2_ACCOUNT_ID"
$AccessKeyId = Resolve-Setting $AccessKeyId "R2_ACCESS_KEY_ID"
$SecretAccessKey = Resolve-Setting $SecretAccessKey "R2_SECRET_ACCESS_KEY"
$PublicBaseUrl = Resolve-Setting $PublicBaseUrl "R2_PUBLIC_BASE_URL" "https://releases.k-era.org"
$Prefix = Resolve-Setting $Prefix "R2_BIOMETRY_OOD_PREFIX" "biometry-ood"
$ToolBasePath = "/" + $ToolBasePath.Trim("/")

if ($DryRun) {
  if ([string]::IsNullOrWhiteSpace($Bucket)) { $Bucket = "dry-run-bucket" }
  if ([string]::IsNullOrWhiteSpace($AccountId)) { $AccountId = "dry-run-account" }
  if ([string]::IsNullOrWhiteSpace($AccessKeyId)) { $AccessKeyId = "dry-run-access-key" }
  if ([string]::IsNullOrWhiteSpace($SecretAccessKey)) { $SecretAccessKey = "dry-run-secret" }
}

Require-Value "R2_BUCKET" $Bucket
Require-Value "R2_ACCOUNT_ID" $AccountId
Require-Value "R2_ACCESS_KEY_ID" $AccessKeyId
Require-Value "R2_SECRET_ACCESS_KEY" $SecretAccessKey
Require-Value "R2_PUBLIC_BASE_URL" $PublicBaseUrl
Require-Value "R2_BIOMETRY_OOD_PREFIX/Prefix" $Prefix

$python = Resolve-PythonExecutable
if (-not $SkipTests) {
  Write-Host "Running Python deployment and model tests..."
  & $python -m unittest discover -s (Join-Path $RepositoryRoot "tests") -p "test_*.py"
  if ($LASTEXITCODE -ne 0) { throw "Python tests failed." }
  Write-Host "Running JavaScript core tests..."
  Push-Location $RepositoryRoot
  try { & node "tests/test_web_core.js" } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "JavaScript tests failed." }
}

Assert-PathInside $RepositoryRoot $ReleaseRoot
if (Test-Path -LiteralPath $ReleaseRoot) { Remove-Item -LiteralPath $ReleaseRoot -Recurse -Force }
[void](New-Item -ItemType Directory -Path $ReleaseRoot -Force)

Write-Host "Building allowlisted static site for $Version..."
& $python (Join-Path $RepositoryRoot "deployment\build_static_site.py") --output $ReleaseRoot
if ($LASTEXITCODE -ne 0) { throw "Static site build failed." }

$model = Get-Content -LiteralPath (Join-Path $ReleaseRoot "models\biometry_ood_bilateral_v32.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$sourceCommit = (& git -C $RepositoryRoot rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { $sourceCommit = "unknown" }
# Reproducibility is determined by files that can change the public bundle;
# release tooling/docs may be edited while publishing an unchanged bundle.
$sourceDirty = -not [string]::IsNullOrWhiteSpace((
  & git -C $RepositoryRoot status --porcelain -- `
    web `
    models/biometry_ood_bilateral_v32.json `
    deployment/build_static_site.py 2>$null | Out-String
))
if ($sourceDirty -and -not $AllowDirtySource -and -not $DryRun) {
  throw "Refusing to publish from a dirty worktree. Commit the release source or pass -AllowDirtySource explicitly."
}
$builtAt = (Get-Date).ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)
$releaseFiles = Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -File | Sort-Object FullName
$fileEntries = foreach ($file in $releaseFiles) {
  $relative = Get-RelativePathCompat $ReleaseRoot $file.FullName
  [ordered]@{
    path = $relative
    bytes = $file.Length
    sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  }
}
$manifest = [ordered]@{
  schema_version = 1
  version = $Version
  model_bundle_version = [string]$model.bundle_version
  built_at_utc = $builtAt
  source_commit = ([string]$sourceCommit).Trim()
  source_worktree_dirty = $sourceDirty
  files = @($fileEntries)
}
Write-JsonFile (Join-Path $ReleaseRoot "manifest.json") $manifest

$releaseObjectPrefix = Join-S3Key @($Prefix, "releases", $Version)
$releaseAlreadyExists = Test-RemoteReleaseExists $manifest
if (-not $releaseAlreadyExists) {
  foreach ($file in Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -File | Sort-Object FullName) {
    $relative = Get-RelativePathCompat $ReleaseRoot $file.FullName
    $objectKey = Join-S3Key @($releaseObjectPrefix, $relative)
    Invoke-R2PutObject -ObjectKey $objectKey -Path $file.FullName -ContentType (Get-ContentType $file.FullName) -CacheControl "public, max-age=31536000, immutable"
  }
}

Invoke-RemoteReleaseCheck $Version

if ($Promote) {
  Assert-PathInside $RepositoryRoot $CurrentRoot
  if (Test-Path -LiteralPath $CurrentRoot) { Remove-Item -LiteralPath $CurrentRoot -Recurse -Force }
  [void](New-Item -ItemType Directory -Path $CurrentRoot -Force)

  $releaseHtml = Get-Content -LiteralPath (Join-Path $ReleaseRoot "web\index.html") -Raw -Encoding UTF8
  $baseHref = "$ToolBasePath/releases/$Version/web/"
  if ($releaseHtml -notmatch "<head>") { throw "Static web index is missing <head>." }
  $currentHtml = $releaseHtml.Replace("base-uri 'none'", "base-uri 'self'")
  if ($currentHtml -notmatch "<title>") { throw "Static web index is missing <title>." }
  $currentHtml = $currentHtml.Replace("  <title>", "  <base href=`"$baseHref`">`n  <title>")
  [System.IO.File]::WriteAllText((Join-Path $CurrentRoot "index.html"), $currentHtml, [System.Text.UTF8Encoding]::new($false))

  $stable = [ordered]@{
    schema_version = 1
    version = $Version
    model_bundle_version = [string]$model.bundle_version
    promoted_at_utc = (Get-Date).ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)
    source_commit = ([string]$sourceCommit).Trim()
    tool_path = $ToolBasePath
    release_manifest_url = "$($PublicBaseUrl.TrimEnd('/'))/$(Join-S3Key @($releaseObjectPrefix, 'manifest.json'))"
  }
  Write-JsonFile (Join-Path $CurrentRoot "stable.json") $stable

  Invoke-R2PutObject -ObjectKey (Join-S3Key @($Prefix, "stable.json")) -Path (Join-Path $CurrentRoot "stable.json") -ContentType "application/json; charset=utf-8" -CacheControl "no-cache, no-store, must-revalidate"
  # The gateway HTML is the release pointer and must be the final write.
  Invoke-R2PutObject -ObjectKey (Join-S3Key @($Prefix, "current", "index.html")) -Path (Join-Path $CurrentRoot "index.html") -ContentType "text/html; charset=utf-8" -CacheControl "no-cache, no-store, must-revalidate"
  Write-Host "promoted: $Version -> $ToolBasePath"
} else {
  Write-Host "published without promotion: $Version"
  Write-Host "Re-run with -Promote after reviewing the versioned release."
}
