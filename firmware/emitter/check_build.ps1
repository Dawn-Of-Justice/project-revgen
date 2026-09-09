param([ValidateSet('c3','classic')][string]$Target = 'c3', [switch]$UseSecrets)
$ErrorActionPreference = 'Stop'
# Compile a staged copy; placeholder credentials unless -UseSecrets is passed.
$buildRoot = Join-Path $PSScriptRoot $(if ($Target -eq 'c3') { 'build/check' } else { 'build/check-classic' })
$fqbn = if ($Target -eq 'c3') { 'esp32:esp32:esp32c3:CDCOnBoot=cdc' } else { 'esp32:esp32:esp32:FlashSize=4M,PSRAM=disabled' }
$sketchRoot = Join-Path $buildRoot 'emitter'
New-Item -ItemType Directory -Force -Path $sketchRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'emitter.ino') -Destination $sketchRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'learning.h'), (Join-Path $PSScriptRoot 'learning_page.h') -Destination $sketchRoot
$configName = if ($UseSecrets) { 'secrets.h' } else { 'secrets.example.h' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $configName))) { throw "Missing $configName" }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot $configName) -Destination (Join-Path $sketchRoot 'secrets.h')
arduino-cli compile --jobs 4 --fqbn $fqbn --build-path (Join-Path $buildRoot 'output') $sketchRoot 2>&1 | Tee-Object -FilePath (Join-Path $buildRoot 'compile.log')
if ($LASTEXITCODE -ne 0) { throw "Emitter $Target compilation failed" }
