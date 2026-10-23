# PowerShell Script to Rename USB Cameras in Windows Registry
# Run this script in PowerShell as Administrator

param(
    [string]$TargetName = "Arducam_ORIGIN"
)

# Elevate script to Administrator if not already elevated
if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsPrincipal][Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Elevating privileges to Administrator..." -ForegroundColor Yellow
    Start-Process powershell.exe -ArgumentList ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`" -TargetName `"{1}`"" -f $PSCommandPath, $TargetName) -Verb RunAs
    exit
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "        USB Camera Renaming Tool (Windows)        " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Find connected Arducam / USB Video devices
$connectedDevices = Get-PnpDevice -Class "Camera","Image" -Status OK -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "USB\VID_0C45*" -or $_.FriendlyName -like "*Arducam*" }

if (-not $connectedDevices) {
    Write-Host "No active Arducam cameras found. Checking all USB cameras..." -ForegroundColor Yellow
    $connectedDevices = Get-PnpDevice -Class "Camera","Image" -Status OK -ErrorAction SilentlyContinue
}

if (-not $connectedDevices) {
    Write-Host "Error: No active USB cameras detected. Please plug in the camera and retry." -ForegroundColor Red
    pause
    exit
}

Write-Host "`nDetected active camera(s):" -ForegroundColor Green
$idx = 1
$devicesList = @($connectedDevices)
foreach ($dev in $devicesList) {
    Write-Host " [$idx] $($dev.FriendlyName) (InstanceId: $($dev.InstanceId))" -ForegroundColor White
    $idx++
}

$chosenDev = $devicesList[0]
if ($devicesList.Count -gt 1) {
    $sel = Read-Host "`nEnter device number to rename [1-$($devicesList.Count)] (Default: 1)"
    if ($sel -match '^\d+$' -and [int]$sel -le $devicesList.Count -and [int]$sel -ge 1) {
        $chosenDev = $devicesList[[int]$sel - 1]
    }
}

Write-Host "`nChoose name for this camera:" -ForegroundColor Yellow
Write-Host " [1] Arducam_ORIGIN  (Dedicated Grommet Camera / Origin 3)" -ForegroundColor White
Write-Host " [2] Arducam_TOP     (Main Top View Camera)" -ForegroundColor White
Write-Host " [3] Custom Name" -ForegroundColor White
$nameChoice = Read-Host "Enter option [1, 2, or 3] (Default: 1)"

$finalName = "Arducam_ORIGIN"
if ($nameChoice -eq "2") {
    $finalName = "Arducam_TOP"
} elseif ($nameChoice -eq "3") {
    $finalName = Read-Host "Enter custom name"
}

$instanceId = $chosenDev.InstanceId
Write-Host "`nTarget Instance: $instanceId" -ForegroundColor Cyan
Write-Host "New Name: $finalName" -ForegroundColor Green

# 1. Grant Administrators FullControl on this registry key using regini
$reginiRule = @"
\Registry\Machine\SYSTEM\CurrentControlSet\Enum\$instanceId [1 17]
"@
$tempFile = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tempFile -Value $reginiRule -Encoding ASCII
regini.exe $tempFile 2>$null
Remove-Item $tempFile -Force -ErrorAction SilentlyContinue

# 2. Update FriendlyName in Registry
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Enum\$instanceId"
try {
    Set-ItemProperty -Path $regPath -Name "FriendlyName" -Value $finalName -ErrorAction Stop
    Write-Host "`n[SUCCESS] Successfully renamed camera to '$finalName'!" -ForegroundColor Green
    Write-Host "Please unplug and re-plug the camera USB cable for Windows to refresh the name." -ForegroundColor Yellow
} catch {
    Write-Host "`nRegistry update error: $_" -ForegroundColor Red
    Write-Host "Trying fallback via reg.exe..." -ForegroundColor Yellow
    & reg.exe add "HKLM\SYSTEM\CurrentControlSet\Enum\$instanceId" /v "FriendlyName" /t REG_SZ /d "$finalName" /f
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[SUCCESS] Renamed camera to '$finalName' via reg.exe!" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Could not update registry key. Permissions may be restricted." -ForegroundColor Red
    }
}

Write-Host "`nPress any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
