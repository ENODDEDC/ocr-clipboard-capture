param(
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Assert-Cmd($cmd) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    throw "Missing command: $cmd"
  }
}

Assert-Cmd py

if ($Clean) {
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

py -m pip install -r requirements.txt
py -m pip install pyinstaller

py .\tools\make_icon.py

py -m PyInstaller .\copy_highlight.spec --noconfirm --clean

Write-Host ""
Write-Host "Built EXE:"
Write-Host "  dist\\ClipOCR\\ClipOCR.exe"

Write-Host ""
Write-Host "Tip: keep the whole folder when distributing:"
Write-Host "  dist\\ClipOCR\\ (contains _internal\\python314.dll)"
