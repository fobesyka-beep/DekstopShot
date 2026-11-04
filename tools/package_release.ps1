param(
    [string]$OutputDirectory = "release"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$distribution = Join-Path $projectRoot "dist\DekstopShot"
$executable = Join-Path $distribution "DekstopShot.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $distribution "_internal") -PathType Container)) {
    throw "Run Build_EXE.cmd first. The full dist\DekstopShot folder is required."
}

$outputPath = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
}
if ($outputPath.StartsWith($distribution + [System.IO.Path]::DirectorySeparatorChar,
                          [System.StringComparison]::OrdinalIgnoreCase) -or $outputPath -eq $distribution) {
    throw "The release archive must be outside the application folder."
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null

# Refresh bundled documentation without changing the tested executable.
foreach ($name in @("README.md", "VALIDATION.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md")) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination (Join-Path $distribution "_internal\$name") -Force
}
$bundledDocs = Join-Path $distribution "_internal\docs"
[System.IO.Directory]::CreateDirectory($bundledDocs) | Out-Null
Copy-Item -Path (Join-Path $projectRoot "docs\*") -Destination $bundledDocs -Recurse -Force
$bundledAssets = Join-Path $distribution "_internal\assets"
[System.IO.Directory]::CreateDirectory($bundledAssets) | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "assets\dekstopshot.png") -Destination $bundledAssets -Force
$archivePath = Join-Path $outputPath "DekstopShot-Windows-x64.zip"
Compress-Archive -LiteralPath $distribution -DestinationPath $archivePath -CompressionLevel Optimal -Force
$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$checksumPath = Join-Path $outputPath "SHA256SUMS.txt"
[System.IO.File]::WriteAllText($checksumPath, "$hash  DekstopShot-Windows-x64.zip`n",
                              [System.Text.UTF8Encoding]::new($false))
Write-Output "Release archive: $archivePath"
Write-Output "SHA256 checksum: $checksumPath"
