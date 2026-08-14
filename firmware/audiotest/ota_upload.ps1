<#
    OTA upload without mDNS.

    Arduino IDE 2.x discovers network ports over mDNS, which Windows blocks or
    drops often enough that it is not worth relying on. This talks straight to
    the device's IP instead, which is the same thing espota does once the IDE
    has found it.

    FIRST: in the Arduino IDE, Sketch > Export Compiled Binary (Ctrl+Alt+S).
    That writes remote.ino.bin into a build/ folder beside the sketch.

    THEN: put the board in maintenance mode -- hold the button, plug in USB,
    keep holding ~3s past "AutoConnect: SUCCESS". Wait for:

        maintenance mode: OTA open for 5 minutes
        ready at 192.168.0.188

    THEN run this from the firmware/remote folder:

        .\ota_upload.ps1 -Ip 192.168.0.188 -Password <OTA_PASSWORD>

    The password is OTA_PASSWORD from secrets.h.
#>

param(
    [Parameter(Mandatory = $true)][string]$Ip,
    [Parameter(Mandatory = $true)][string]$Password,
    [string]$Bin,
    [int]$Port = 3232
)

$ErrorActionPreference = "Stop"

# --- find espota ---------------------------------------------------------
# Lives under packages\esp32\hardware\esp32\<version>\tools\, which is why the
# earlier search under \tools\ came up empty.
Write-Host "locating espota..." -ForegroundColor Cyan
$espota = Get-ChildItem "$env:LOCALAPPDATA\Arduino15" -Recurse -File -ErrorAction SilentlyContinue |
          Where-Object { $_.Name -in @("espota.exe", "espota.py") } |
          Sort-Object LastWriteTime -Descending |
          Select-Object -First 1

if (-not $espota) {
    throw "espota not found under $env:LOCALAPPDATA\Arduino15. Is the ESP32 board package installed?"
}
Write-Host "  $($espota.FullName)"

# --- find the binary -----------------------------------------------------
if (-not $Bin) {
    Write-Host "locating most recent .bin..." -ForegroundColor Cyan
    $candidate = Get-ChildItem $PSScriptRoot -Recurse -Filter "*.ino.bin" -ErrorAction SilentlyContinue |
                 Sort-Object LastWriteTime -Descending |
                 Select-Object -First 1
    if (-not $candidate) {
        throw "No .ino.bin found under $PSScriptRoot. Run Sketch > Export Compiled Binary first."
    }
    $Bin = $candidate.FullName
}

$age = [int]((Get-Date) - (Get-Item $Bin).LastWriteTime).TotalMinutes
Write-Host "  $Bin"
Write-Host "  built $age minute(s) ago, $([math]::Round((Get-Item $Bin).Length / 1KB)) KB"
if ($age -gt 10) {
    Write-Host "  NOTE: that binary is not fresh. Re-export if you have edited the sketch." -ForegroundColor Yellow
}

# --- reachable? ----------------------------------------------------------
Write-Host "checking $Ip is awake..." -ForegroundColor Cyan
if (-not (Test-Connection -ComputerName $Ip -Count 1 -Quiet -ErrorAction SilentlyContinue)) {
    Write-Host "  no ping response." -ForegroundColor Yellow
    Write-Host "  The device sleeps after 5 minutes. Hold the button and reset to re-arm." -ForegroundColor Yellow
}

# --- upload --------------------------------------------------------------
Write-Host "uploading..." -ForegroundColor Cyan
$espotaArgs = @("-i", $Ip, "-p", $Port, "-a", $Password, "-f", $Bin, "-r", "-d")

if ($espota.Extension -eq ".py") {
    $py = Get-ChildItem "$env:LOCALAPPDATA\Arduino15" -Recurse -File -ErrorAction SilentlyContinue |
          Where-Object { $_.Name -eq "python.exe" } | Select-Object -First 1
    $exe = if ($py) { $py.FullName } else { "python" }
    & $exe $espota.FullName @espotaArgs
} else {
    & $espota.FullName @espotaArgs
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`ndone -- the board reboots into the new firmware." -ForegroundColor Green
} else {
    Write-Host "`nfailed (exit $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "  'No response from device'  -> it is asleep, or the IP changed"
    Write-Host "  'Authentication Failed'    -> password does not match OTA_PASSWORD in secrets.h"
    Write-Host "  'Not Enough Space'         -> Partition Scheme has no OTA slot; use 8M with spiffs"
}
