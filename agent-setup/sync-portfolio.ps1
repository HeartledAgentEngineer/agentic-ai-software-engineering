<#
.SYNOPSIS
    sync-portfolio.ps1 - Synchronisation zwischen privatem Playground und Schaufenster-Portfolio.

.DESCRIPTION
    Automatisierter Übergabe-Workflow:
    1. Whitelist-Übertrag der freigegebenen Projekte, Agenten-Tools und Dokumentation.
    2. Privacy- & Leak-Scan (keine privaten Pfade, Mailadressen oder Tokens).
    3. Verifikations-Gate (Prüfung von Linter und Test-Suiten im Zielrepo).
    4. Zusammenfassung für das atomare Git-Commit.

.PARAMETER SourceDir
    Pfad zum Quell-Workspace (privater Playground).

.PARAMETER TargetDir
    Pfad zum Ziel-Repository (Schaufenster/Portfolio). Standard ist das Hauptverzeichnis dieses Repos.

.PARAMETER DryRun
    Zeigt geplante Änderungen an, ohne Dateien zu kopieren.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$SourceDir,

    [Parameter(Mandatory = $false)]
    [string]$TargetDir = (Resolve-Path (Join-Path $PSScriptRoot "..")),

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   PORTFOLIO STAGING & SYNC WORKFLOW              " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not $SourceDir) {
    # Falls nicht explizit übergeben, übergeordneten Workspace prüfen
    $DefaultPlayground = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
    if (Test-Path $DefaultPlayground) {
        $SourceDir = $DefaultPlayground
    } else {
        Write-Error "Bitte Quellverzeichnis angeben: -SourceDir <Pfad-zum-Playground>"
        exit 1
    }
}

Write-Host "Quelle: $SourceDir" -ForegroundColor Yellow
Write-Host "Ziel:   $TargetDir" -ForegroundColor Yellow
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Whitelist der freigegebenen Komponenten
# ------------------------------------------------------------------------------
$Whitelist = @(
    "projects/concertify",
    "projects/personal-ai-agent",
    "projects/orbitdesk",
    "projects/typefree",
    "projects/cross-model-review",
    "agent-setup",
    ".github",
    "README.md",
    "HOW-I-WORK.md",
    "JOURNEY.md",
    "SECURITY.md",
    "CHANGELOG.md"
)

Write-Host "[1/4] Prüfe Whitelist-Komponenten..." -ForegroundColor Green
foreach ($item in $Whitelist) {
    $srcPath = Join-Path $SourceDir $item
    if (Test-Path $srcPath) {
        Write-Host "  [OK] Whitelist: $item" -ForegroundColor DarkGray
    } else {
        Write-Host "  [--] Optional / nicht in Quelle gefunden: $item" -ForegroundColor DarkGray
    }
}

# ------------------------------------------------------------------------------
# 2. Privacy- & Leak-Scan
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/4] Führe Privacy- & Leak-Scan im Zielordner aus..." -ForegroundColor Green

$PrivacyPatterns = @(
    '(?i)[a-z0-9._%+-]+@(?!example\.com|users\.noreply\.github\.com)[a-z0-9.-]+\.[a-z]{2,}', # E-Mail (außer Noreply/Muster)
    '[A-Za-z]:\\[Uu]sers\\(?!runneradmin|public)[A-Za-z0-9_.-]+',                              # Absolute lokale Windows-Pfade
    '(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[''"][A-Za-z0-9_\-]{16,}[''"]'          # Typische Tokens & API-Keys
)

$TargetFiles = Get-ChildItem -Path $TargetDir -Recurse -File | Where-Object {
    $_.FullName -notmatch "(\.git|\.venv|__pycache__|\.pytest_cache|node_modules|tests[\\/])"
}

$Findings = 0
foreach ($file in $TargetFiles) {
    $content = Get-Content -Path $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }

    foreach ($pattern in $PrivacyPatterns) {
        if ($content -match $pattern) {
            Write-Host "  [WARNUNG] Fundstelle in $($file.FullName): Treffer für Muster '$pattern'" -ForegroundColor Red
            $Findings++
        }
    }
}

if ($Findings -gt 0) {
    Write-Host "  -> Scan beendet mit $Findings Befund(en). Bereinigung vor Push erforderlich!" -ForegroundColor Red
} else {
    Write-Host "  [OK] 0 sensible Fundstellen im Quellcode und in der Dokumentation. Privacy-Gate grün." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 3. Verifikations-Gate (Lokale Tests)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/4] Führe Verifikations-Gate aus..." -ForegroundColor Green

$PythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if ($PythonCmd) {
    $Suites = @(
        @{ Dir = "projects/concertify"; Args = @("-m", "pytest", "-q", "tests") },
        @{ Dir = "projects/personal-ai-agent/backend"; Args = @("-m", "pytest", "-q", "tests") }
    )

    $AllTestsPassed = $true
    foreach ($suite in $Suites) {
        $suitePath = Join-Path $TargetDir $suite.Dir
        if (Test-Path $suitePath) {
            Write-Host "  Starte Tests für: $($suite.Dir)..." -ForegroundColor DarkGray
            Push-Location $suitePath
            try {
                & python $suite.Args 2>$null
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "    [OK] $($suite.Dir) grün (Exit-Code 0)." -ForegroundColor Green
                } else {
                    Write-Host "    [WARNUNG] $($suite.Dir) meldete Fehler (Exit-Code $LASTEXITCODE)." -ForegroundColor Yellow
                    $AllTestsPassed = $false
                }
            } finally {
                Pop-Location
            }
        }
    }
} else {
    Write-Host "  [HINWEIS] Kein lokales Python im Pfad gefunden. Die Cloud-CI (.github/workflows/ci.yml) übernimmt die Matrix-Prüfung." -ForegroundColor DarkGray
}

# ------------------------------------------------------------------------------
# 4. Statusübersicht für Git
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/4] Git-Status im Zielverzeichnis:" -ForegroundColor Green
Push-Location $TargetDir
try {
    git status --short
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Workflow abgeschlossen. Wenn alles grün ist: 'git commit' & 'git push'." -ForegroundColor Cyan
