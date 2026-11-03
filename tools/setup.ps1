param(
    [ValidateSet("Run", "Build")]
    [string]$Action = "Run"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Program" }
}

try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $localPython = Join-Path $projectRoot ".python312\python.exe"
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $localPython) {
            Invoke-Checked -Program $localPython -Arguments @("-m", "venv", ".venv")
        } elseif ($launcher) {
            $pythonSelector = $null
            foreach ($candidate in @("-3.12", "-3.13", "-3.11", "-3.10")) {
                try {
                    & $launcher.Source $candidate -c "import sys; assert (3,10) <= sys.version_info[:2] < (3,14)" 2>$null
                } catch { continue }
                if ($LASTEXITCODE -eq 0) { $pythonSelector = $candidate; break }
            }
            if (-not $pythonSelector) { throw "Install Python 3.12 x64 from python.org, then try again." }
            Invoke-Checked -Program $launcher.Source -Arguments @($pythonSelector, "-m", "venv", ".venv")
        } else {
            $python = Get-Command python -ErrorAction SilentlyContinue
            if (-not $python) { throw "Install Python 3.12 x64 from python.org (Add Python to PATH)." }
            Invoke-Checked -Program $python.Source -Arguments @("-c", "import sys; assert (3,10) <= sys.version_info[:2] < (3,14)")
            Invoke-Checked -Program $python.Source -Arguments @("-m", "venv", ".venv")
        }
    }
    Invoke-Checked -Program $venvPython -Arguments @("-c", "import struct,sys; assert struct.calcsize('P') == 8, 'Python x64 is required'; assert (3,10) <= sys.version_info[:2] < (3,14), 'Python 3.10-3.13 is required'")
    $requirementsName = if ($Action -eq "Build") { "requirements-build.txt" } else { "requirements.txt" }
    Write-Host "Preparing DekstopShot dependencies. Internet is needed on first run."
    Invoke-Checked -Program $venvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", $requirementsName)

    if ($Action -eq "Build") {
        Invoke-Checked -Program $venvPython -Arguments @("-m", "ruff", "check", ".")
        Invoke-Checked -Program $venvPython -Arguments @("-m", "pytest", "-q")
        Invoke-Checked -Program $venvPython -Arguments @("tools\make_icon.py")
        Invoke-Checked -Program $venvPython -Arguments @("tools\collect_licenses.py")
        Invoke-Checked -Program $venvPython -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "DekstopShot.spec")
        Write-Host "Build complete: dist\DekstopShot\DekstopShot.exe"
        Write-Host "Copy the entire dist\DekstopShot folder when sharing the app."
    } else {
        $pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
        $entryPoint = Join-Path $projectRoot "main.py"
        Start-Process -FilePath $pythonw -ArgumentList ('"' + $entryPoint + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden
        Write-Host "DekstopShot started. Look for its icon next to the clock."
    }
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "See README.md for manual installation and troubleshooting."
    exit 1
}
