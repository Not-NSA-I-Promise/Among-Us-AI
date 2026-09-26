# Forces Among Us to a 1920x1080 16:9 window, which the task solvers require.
# MUST be run with the game CLOSED - the game overwrites its own settings on exit.
$ErrorActionPreference = 'Stop'

if (Get-Process -Name "Among Us" -ErrorAction SilentlyContinue) {
    Write-Output "[ERROR] Among Us is still running. Close it first, then run this again."
    exit 1
}

$rk = "HKCU:\Software\InnerSloth\Among Us"
if (-not (Test-Path $rk)) {
    Write-Output "[ERROR] PlayerPrefs registry key not found: $rk"
    Write-Output "        Launch the game once, close it, then run this again."
    exit 1
}

$map = @{
    "Screenmanager Resolution Width_h182942802"          = 1920
    "Screenmanager Resolution Height_h2627697771"        = 1080
    "Screenmanager Resolution Window Width_h2524650974"  = 1920
    "Screenmanager Resolution Window Height_h1684712807" = 1080
    "Screenmanager Fullscreen mode_h3630240806"          = 3
    "Screenmanager Stereo 3D_h1665754519"               = 0
}

foreach ($k in $map.Keys) {
    $before = (Get-ItemProperty $rk).$k
    Set-ItemProperty -Path $rk -Name $k -Value $map[$k] -Type DWord
    Write-Output ("  {0,-52} {1} -> {2}" -f $k, $before, $map[$k])
}

Write-Output ""
Write-Output "[OK] Set to 1920x1080 windowed. Start the game to apply."
