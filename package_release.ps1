$ErrorActionPreference = "Stop"

$srcDir = Resolve-Path .\dist\ClipOCR
$outDir = Resolve-Path .
$zipPath = Join-Path $outDir "ClipOCR-win64.zip"

if (Test-Path $zipPath) { Remove-Item -Force $zipPath }

Compress-Archive -Path (Join-Path $srcDir "*") -DestinationPath $zipPath

Write-Host "Created:"
Write-Host "  $zipPath"

