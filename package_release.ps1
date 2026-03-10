param(
  [switch]$BundleTesseract,
  [string]$TesseractExe
)

$ErrorActionPreference = "Stop"

function Find-TesseractExe {
  param([string]$Hint)

  if ($Hint -and (Test-Path $Hint)) { return (Resolve-Path $Hint).Path }
  if ($env:TESSERACT_CMD -and (Test-Path $env:TESSERACT_CMD)) { return (Resolve-Path $env:TESSERACT_CMD).Path }

  $candidates = @(
    "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    "C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) { return (Resolve-Path $c).Path }
  }

  $cmd = Get-Command tesseract -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Path }

  return $null
}

$srcDir = Resolve-Path .\dist\ClipOCR

if ($BundleTesseract) {
  $exe = Find-TesseractExe -Hint $TesseractExe
  if (-not $exe) {
    throw "Tesseract not found. Install it first, or pass -TesseractExe 'C:\\Path\\To\\tesseract.exe'."
  }

  $tessDir = Split-Path -Parent $exe
  $dest = Join-Path $srcDir "tesseract"

  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $dest
  Copy-Item -Recurse -Force $tessDir $dest

  Write-Host "Bundled Tesseract from:"
  Write-Host "  $tessDir"
}

$outDir = Resolve-Path .
$zipPath = Join-Path $outDir "ClipOCR-win64.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }

Compress-Archive -Path (Join-Path $srcDir "*") -DestinationPath $zipPath

Write-Host "Created:"
Write-Host "  $zipPath"
