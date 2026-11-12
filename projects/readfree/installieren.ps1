# Installiert readFREE fuer den aktuellen Benutzer oder entfernt es.
#
#   .\installieren.ps1             kopiert, richtet den Autostart ein, startet
#   .\installieren.ps1 -Entfernen  beendet, entfernt Autostart und Programmordner
#
# Nur im Benutzerbereich: Programmordner unter %LOCALAPPDATA%, Autostart unter HKCU.
# Eine Installation unter dem frueheren Namen "Markierung vorlesen" wird abgeloest.
param(
    [switch]$Entfernen,
    [switch]$OhneAutostart,
    [switch]$NichtStarten,
    [string]$Ziel = (Join-Path $env:LOCALAPPDATA 'hermes\werkzeuge\readfree')
)
$ErrorActionPreference = 'Stop'
$RunSchluessel = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$RunName = 'readFREE'

function Stoppe-Prozess([string]$Skript) {
    $muster = '*' + $Skript + '*'
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
        Where-Object { $_.CommandLine -like $muster } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

function Loese-Altstand-Ab {
    $hermes = Join-Path $env:LOCALAPPDATA 'hermes'
    $altOrdner = Join-Path $hermes 'werkzeuge\markierung_vorlesen'
    Stoppe-Prozess (Join-Path $altOrdner 'markierung_vorlesen.py')
    Remove-ItemProperty -Path $RunSchluessel -Name 'MarkierungVorlesen' -ErrorAction SilentlyContinue
    foreach ($ordner in $altOrdner, (Join-Path $hermes 'cache\markierung_vorlesen')) {
        if (Test-Path $ordner) { Remove-Item -LiteralPath $ordner -Recurse -Force }
    }
}

Stoppe-Prozess (Join-Path $Ziel 'readfree.py')
# Ein Test mit -Ziel darf die echte Installation nicht anfassen.
if (-not $PSBoundParameters.ContainsKey('Ziel')) { Loese-Altstand-Ab }

if ($Entfernen) {
    if (-not $OhneAutostart) {
        Remove-ItemProperty -Path $RunSchluessel -Name $RunName -ErrorAction SilentlyContinue
    }
    if (Test-Path $Ziel) { Remove-Item -LiteralPath $Ziel -Recurse -Force }
    Write-Output 'Entfernt.'
    exit 0
}

$quelle = $PSScriptRoot
$modul = @('..\..\02_Softwareentwicklung_IT\typeFREE\windows\zwischenablage.py', '..\typefree\windows\zwischenablage.py') |
    ForEach-Object { Join-Path $quelle $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $modul) { throw 'zwischenablage.py aus typeFREE nicht gefunden.' }
New-Item -ItemType Directory -Path $Ziel -Force | Out-Null
foreach ($name in 'kern.py', 'erfassen.py', 'ausgabe.py', 'fenster.py', 'readfree.py') {
    Copy-Item -LiteralPath (Join-Path $quelle $name) -Destination $Ziel -Force
}
Copy-Item -LiteralPath $modul -Destination $Ziel -Force

$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { throw 'pythonw.exe nicht gefunden.' }
$skript = Join-Path $Ziel 'readfree.py'

if (-not $OhneAutostart) {
    Set-ItemProperty -Path $RunSchluessel -Name $RunName -Value ('"{0}" "{1}"' -f $pythonw, $skript)
}
if (-not $NichtStarten) {
    Start-Process -FilePath $pythonw -ArgumentList ('"{0}"' -f $skript) -WorkingDirectory $Ziel
}
Write-Output "Installiert: $Ziel"
