# Provision the exact worker interpreter independently of the CIW harness.
# This verifies an upstream archive, not a complete SCR runtime qualification.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Destination,
    [Parameter(Mandatory = $true)][string]$AuditPath
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$uri = 'https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-pc-windows-msvc-install_only.tar.gz'
$expected = 'c5303174bc29f5205decf6721ac549d4eb41c448f9b8c46cbc562d00348865bb'
# A fresh directory prevents an earlier environment from contaminating the closure.
New-Item -ItemType Directory -Path $Destination -ErrorAction Stop | Out-Null
$archive = Join-Path $Destination 'python-runtime.tar.gz'
$observation = @{
    source = $uri
    archive_sha256_expected = $expected
    status = 'started'
    full_runtime_qualification = 'not_performed'
}
try {
    Invoke-WebRequest -Uri $uri -OutFile $archive
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $observation.archive_sha256_observed = $actual
    if ($actual -ne $expected) { throw 'Python archive digest mismatch' }
    tar -xzf $archive -C $Destination
    if ($LASTEXITCODE -ne 0) { throw 'Python archive extraction failed' }
    $workerBase = Join-Path $Destination 'python/python.exe'
    $identityJson = & $workerBase -I -c 'import json,platform,struct,sys; print(json.dumps({"version":platform.python_version(),"implementation":sys.implementation.name,"platform":sys.platform,"bits":struct.calcsize("P")*8}))'
    if ($LASTEXITCODE -ne 0) { throw 'Python identity probe failed' }
    $identity = $identityJson | ConvertFrom-Json
    $observation.identity = $identity
    $observation.executable_sha256 = (Get-FileHash -LiteralPath $workerBase -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($identity.version -ne '3.12.14' -or $identity.implementation -ne 'cpython' -or $identity.platform -ne 'win32' -or $identity.bits -ne 64) {
        throw 'Python interpreter does not match the required Windows x64 CPython 3.12.14 identity'
    }
    $observation.status = 'archive_and_interpreter_checked'
    Write-Output $workerBase
}
catch {
    $observation.status = 'failed'
    $observation.reason = $_.Exception.Message
    throw
}
finally {
    $observation | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $AuditPath
}
