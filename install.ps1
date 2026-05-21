# OpenContext Runtime Installer for Windows (PowerShell)
# One-liner: irm https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.ps1 | iex

param(
    [string]$Version = "0.1.0",
    [string]$RepoUrl = "https://github.com/CesarMSFelipe/OpenContext-Runtime"
)

$ErrorActionPreference = "Stop"

function Test-Python {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
    }
    if (-not $pythonCmd) {
        Write-Host "Error: Python 3 is required but not found." -ForegroundColor Red
        Write-Host "Please install Python 3.12 or later from https://python.org"
        exit 1
    }

    $pyVersion = & $pythonCmd.Source --version 2>&1
    $versionMatch = $pyVersion -match 'Python (\d+)\.(\d+)'
    if (-not $versionMatch) {
        Write-Host "Error: Could not determine Python version." -ForegroundColor Red
        exit 1
    }

    $major = [int]$matches[1]
    $minor = [int]$matches[2]

    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 12)) {
        Write-Host "Error: Python 3.12+ is required. Found: $pyVersion" -ForegroundColor Red
        exit 1
    }

    Write-Host "✓ $pyVersion" -ForegroundColor Green
    return $pythonCmd.Source
}

function Test-Pip {
    param([string]$PythonCmd)
    try {
        & $PythonCmd -m pip --version | Out-Null
        Write-Host "✓ pip" -ForegroundColor Green
    } catch {
        Write-Host "Error: pip is required but not found." -ForegroundColor Red
        exit 1
    }
}

function Install-OpenContext {
    $pythonCmd = Test-Python
    Test-Pip -PythonCmd $pythonCmd

    Write-Host ""
    Write-Host "Installing OpenContext packages..." -ForegroundColor Cyan
    Write-Host ""

    # Try pip install first
    try {
        & $pythonCmd -m pip install opencontext-core opencontext-cli --quiet 2>$null
        Write-Host "✓ Installed from PyPI" -ForegroundColor Green
    } catch {
        Write-Host "PyPI packages not found. Installing from source..." -ForegroundColor Yellow
        Write-Host "This requires git." -ForegroundColor Yellow

        $gitCmd = Get-Command git -ErrorAction SilentlyContinue
        if (-not $gitCmd) {
            Write-Host "Error: git is required for source installation." -ForegroundColor Red
            Write-Host ""
            Write-Host "Manual installation:" -ForegroundColor Yellow
            Write-Host "  git clone $RepoUrl.git" -ForegroundColor Yellow
            Write-Host "  cd OpenContext-Runtime" -ForegroundColor Yellow
            Write-Host "  pip install -e packages\opencontext_core -e packages\opencontext_cli" -ForegroundColor Yellow
            exit 1
        }

        $tempDir = [System.IO.Path]::GetTempPath() + [System.Guid]::NewGuid().ToString()
        New-Item -ItemType Directory -Path $tempDir | Out-Null

        try {
            git clone --depth 1 "$RepoUrl.git" "$tempDir\opencontext" 2>$null
            Set-Location "$tempDir\opencontext"
            & $pythonCmd -m pip install -e packages\opencontext_core -e packages\opencontext_cli --quiet
            Write-Host "✓ Installed from source" -ForegroundColor Green
        } catch {
            Write-Host "Error: Could not install from source." -ForegroundColor Red
            exit 1
        }
    }

    # Check if opencontext is in PATH
    $opencontextCmd = Get-Command opencontext -ErrorAction SilentlyContinue
    if (-not $opencontextCmd) {
        Write-Host ""
        Write-Host "Warning: 'opencontext' command not found in PATH." -ForegroundColor Yellow
        Write-Host "You may need to add Python scripts directory to your PATH." -ForegroundColor Yellow
        Write-Host ""
    }

    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "OpenContext Runtime v$Version is installed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Quick start:" -ForegroundColor White
    Write-Host "  1. cd your-project" -ForegroundColor Gray
    Write-Host "  2. opencontext onboard" -ForegroundColor Gray
    Write-Host "  3. opencontext index ." -ForegroundColor Gray
    Write-Host "  4. opencontext pack . --query 'Explain this code'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Get help:" -ForegroundColor White
    Write-Host "  opencontext --help" -ForegroundColor Gray
    Write-Host "  opencontext --version" -ForegroundColor Gray
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
}

Install-OpenContext
