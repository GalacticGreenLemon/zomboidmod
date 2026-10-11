@echo off
rem Downloads the latest Viewpoint Model Fix from GitHub and installs it into Zomboid\mods,
rem replacing the old copy. Run it again whenever there is an update. Close the game first.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$url = 'https://github.com/GalacticGreenLemon/zomboidmod/archive/refs/heads/claude/friendly-hypatia-cc8cpl.zip';" ^
  "$mods = Join-Path $env:USERPROFILE 'Zomboid\mods';" ^
  "$tmp = Join-Path $env:TEMP 'ViewpointModelFix-update';" ^
  "if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force };" ^
  "New-Item -ItemType Directory $tmp | Out-Null;" ^
  "Write-Host 'Downloading...';" ^
  "Invoke-WebRequest $url -OutFile (Join-Path $tmp 'mod.zip') -UseBasicParsing;" ^
  "Expand-Archive (Join-Path $tmp 'mod.zip') $tmp;" ^
  "$src = Get-ChildItem $tmp -Directory | Select-Object -First 1;" ^
  "$mod = Join-Path $src.FullName 'Contents\mods\ViewpointModelFix';" ^
  "New-Item -ItemType Directory $mods -Force | Out-Null;" ^
  "$dest = Join-Path $mods 'ViewpointModelFix';" ^
  "if (Test-Path $dest) { Remove-Item $dest -Recurse -Force };" ^
  "Copy-Item $mod $dest -Recurse;" ^
  "Remove-Item $tmp -Recurse -Force;" ^
  "Write-Host ('Installed to ' + $dest)"
if errorlevel 1 (echo. & echo Something went wrong, see the message above.)
pause
