param([switch]$Test,[switch]$AutoStart)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.DataWriter,Windows.Storage.Streams,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
function Await($op,[type]$type) {
  $m = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
  $task=$m.MakeGenericMethod($type).Invoke($null,@($op)); $task.Wait(); return $task.Result
}
# Der Windows-Player gibt ueber 2x keinen Ton mehr aus (gemessen 09.11.2026). Hoehere Tempi kommen daher
# zum Teil aus der Audiodatei: Datei-Tempo mal Player-Tempo ergibt das gewaehlte Tempo.
function Get-FileFactor([double]$speed) { if ($speed -gt 2) { return 1.5 } else { return 1.0 } }
function Get-PlayerRate([double]$speed,[double]$fileFactor) { return [Math]::Min(2.0,$speed/$fileFactor) }
function Read-Image($image,$language) {
  $memory=[System.IO.MemoryStream]::new()
  try {
    $image.Save($memory,[System.Drawing.Imaging.ImageFormat]::Png)
    $stream=[Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
    $writer=[Windows.Storage.Streams.DataWriter]::new($stream.GetOutputStreamAt(0))
    $writer.WriteBytes($memory.ToArray())
    [void](Await ($writer.StoreAsync()) ([uint32]))
    [void](Await ($writer.FlushAsync()) ([bool]))
    [void]$writer.DetachStream(); $stream.Seek(0)
    $decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap=Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($language))
    if(-not $engine) { throw "OCR-Sprache $language nicht installiert." }
    $result=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    return $result.Text
  } finally { $memory.Dispose() }
}
# Fingerabdruck des Bildinhalts: gleiche Pixel ergeben dieselbe Kennung. Damit
# erkennt die Automatik, wenn die Zwischenablage nur ALTEN Inhalt zurueckbekommen
# hat (z. B. typeFREE stellt nach dem Einfuegen den Vorinhalt wieder her).
# Nur die Farbwerte zaehlen (24 bit, ohne Alphakanal und ohne Zeilen-Fuellbytes):
# Kommt dasselbe Bild in einem anderen Format zurueck (DIB statt DIBV5), bleibt
# die Kennung gleich.
function Get-BildKennung($bild) {
  $rect=[System.Drawing.Rectangle]::new(0,0,$bild.Width,$bild.Height)
  $daten=$bild.LockBits($rect,[System.Drawing.Imaging.ImageLockMode]::ReadOnly,[System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
  try {
    $zeile=$bild.Width*3
    $bytes=[byte[]]::new($zeile*$bild.Height+8)
    [System.BitConverter]::GetBytes([int]$bild.Width).CopyTo($bytes,$zeile*$bild.Height)
    [System.BitConverter]::GetBytes([int]$bild.Height).CopyTo($bytes,$zeile*$bild.Height+4)
    for ($y=0; $y -lt $bild.Height; $y++) {
      [System.Runtime.InteropServices.Marshal]::Copy([IntPtr]::Add($daten.Scan0,$y*$daten.Stride),$bytes,$y*$zeile,$zeile)
    }
  } finally { $bild.UnlockBits($daten) }
  $sha=[System.Security.Cryptography.SHA256]::Create()
  try { return [System.BitConverter]::ToString($sha.ComputeHash($bytes)) } finally { $sha.Dispose() }
}
# Ein Screenshot legt NUR Bildformate ab. Kopiert man in Excel, Word, OneNote,
# Teams oder im Browser, kommt zum Bild immer Text, HTML oder ein Programmformat
# dazu - das ist kein Screenshot und wird nicht automatisch vorgelesen. Ebenso
# nicht, was typeFREE gerade einfuegt (eigene Marke typeFREE.*).
$script:FremdFormate='^(Text|UnicodeText|OEMText|Locale|Rich Text Format|HTML Format|FileDrop|FileName|FileNameW|Shell IDList Array|Csv|XML Spreadsheet|Biff\d*|Object Descriptor|Link Source|Link Source Descriptor|Embed Source|EnhancedMetafile|MetaFilePict|Hyperlink|Art::.*|Chromium .*|text/.*|typeFREE\..*)$'
function Test-NurBild([string[]]$formate) {
  foreach ($f in $formate) { if ($f -match $script:FremdFormate) { return $false } }
  return $true
}
# Reine Regeln der Automatik - ohne Fenster pruefbar (siehe -Test).
# $bekannt: Kennungen der Bilder, die schon vorgelesen wurden oder beim Einschalten
# schon da waren (die letzten 30) - nicht nur das zuletzt gelesene.
function Get-AutomatikEntscheidung([long]$alt,[long]$neu,[bool]$hatBild,[bool]$nurBild,[string]$kennung,[string[]]$bekannt) {
  if ($neu -eq $alt) { return 'unveraendert' }
  if (-not $hatBild) { return 'keinbild' }
  if (-not $nurBild) { return 'keinScreenshot' }
  if ($kennung -and $bekannt -contains $kennung) { return 'bekanntesBild' }
  return 'lesen'
}
$script:bekannteBilder=New-Object System.Collections.Generic.List[string]
function Add-BekanntesBild([string]$kennung) {
  if (-not $kennung -or $script:bekannteBilder.Contains($kennung)) { return }
  $script:bekannteBilder.Add($kennung)
  while ($script:bekannteBilder.Count -gt 30) { $script:bekannteBilder.RemoveAt(0) }
}
# Entscheidungsprotokoll: nur Zeit, Entscheidung, Formatnamen und Kennungsanfang -
# nie Bild- oder Textinhalte. Haelt die letzten 1000 Zeilen.
function Write-Protokoll([string]$zeile) {
  try {
    $datei=Join-Path $env:LOCALAPPDATA 'hermes\werkzeuge\shotreader.log'
    Add-Content -LiteralPath $datei -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+' '+$zeile) -Encoding UTF8
    if ((Get-Item -LiteralPath $datei).Length -gt 262144) {
      $rest=Get-Content -LiteralPath $datei -Tail 1000 -Encoding UTF8
      Set-Content -LiteralPath $datei -Value $rest -Encoding UTF8
    }
  } catch {}
}
if ($Test) {
  foreach ($fall in @(@(1.0,1.0,1.0),@(1.25,1.0,1.25),@(2.0,1.0,2.0),@(2.25,1.5,1.5),@(3.0,1.5,2.0))) {
    $f=Get-FileFactor $fall[0]; $r=Get-PlayerRate $fall[0] $f
    if ($f -ne $fall[1] -or [Math]::Abs($r-$fall[2]) -gt 0.001) { Write-Output "Tempo falsch bei $($fall[0]): Datei $f, Player $r"; exit 1 }
  }
  if ((Get-PlayerRate 3.0 1.0) -ne 2.0) { Write-Output 'Tempo-Grenze fehlt'; exit 1 }
  $bildA=[System.Drawing.Bitmap]::new(8,8); $bildA.SetPixel(3,3,[System.Drawing.Color]::Red)
  $bildB=[System.Drawing.Bitmap]::new(8,8); $bildB.SetPixel(3,3,[System.Drawing.Color]::Red)
  $bildC=[System.Drawing.Bitmap]::new(8,8); $bildC.SetPixel(4,3,[System.Drawing.Color]::Red)
  $kennungA=Get-BildKennung $bildA; $kennungB=Get-BildKennung $bildB; $kennungC=Get-BildKennung $bildC
  $bildA.Dispose(); $bildB.Dispose(); $bildC.Dispose()
  if ($kennungA -ne $kennungB) { Write-Output 'Bildkennung ist nicht stabil'; exit 1 }
  if ($kennungA -eq $kennungC) { Write-Output 'Bildkennung unterscheidet Inhalte nicht'; exit 1 }
  # Bildkennung ohne Alphakanal: gleiche Farben, anderer Alphawert -> gleiche Kennung
  $bildD=[System.Drawing.Bitmap]::new(8,8); $bildD.SetPixel(3,3,[System.Drawing.Color]::FromArgb(255,200,10,10))
  $bildE=[System.Drawing.Bitmap]::new(8,8,[System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
  $g=[System.Drawing.Graphics]::FromImage($bildE); $g.Clear([System.Drawing.Color]::Black); $g.Dispose()
  $bildD2=[System.Drawing.Bitmap]::new(8,8,[System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
  $g=[System.Drawing.Graphics]::FromImage($bildD2); $g.Clear([System.Drawing.Color]::Black); $g.Dispose(); $bildD2.SetPixel(3,3,[System.Drawing.Color]::FromArgb(255,200,10,10))
  $bildD3=[System.Drawing.Bitmap]::new(8,8); $bildD3.SetPixel(3,3,[System.Drawing.Color]::FromArgb(255,200,10,10))
  for ($x=0;$x -lt 8;$x++){ for($y=0;$y -lt 8;$y++){ if(-not($x -eq 3 -and $y -eq 3)){ $bildD3.SetPixel($x,$y,[System.Drawing.Color]::FromArgb(255,0,0,0)) } } }
  if ((Get-BildKennung $bildD3) -ne (Get-BildKennung $bildD2)) { Write-Output 'Bildkennung haengt vom Pixelformat ab'; exit 1 }
  $bildF=[System.Drawing.Bitmap]::new(8,4); $bildG=[System.Drawing.Bitmap]::new(4,8)
  if ((Get-BildKennung $bildF) -eq (Get-BildKennung $bildG)) { Write-Output 'Bildkennung unterscheidet Groessen nicht'; exit 1 }
  $bildD.Dispose(); $bildE.Dispose(); $bildD2.Dispose(); $bildD3.Dispose(); $bildF.Dispose(); $bildG.Dispose()
  # Formate: Screenshot (nur Bild) gegen Kopie aus Office/Browser/typeFREE
  $formatFaelle=@(
    @(@('Bitmap','DeviceIndependentBitmap','Format17'),$true),
    @(@('PNG','DeviceIndependentBitmap','Bitmap'),$true),
    @(@('Bitmap','UnicodeText','Text','HTML Format'),$false),
    @(@('Biff12','EnhancedMetafile','Bitmap','Csv','Rich Text Format'),$false),
    @(@('HTML Format','Chromium internal source URL','DeviceIndependentBitmap'),$false),
    @(@('UnicodeText','typeFREE.Einfuegemarke'),$false)
  )
  foreach ($fall in $formatFaelle) {
    if ((Test-NurBild $fall[0]) -ne $fall[1]) { Write-Output ('Format-Regel falsch bei '+($fall[0] -join ',')); exit 1 }
  }
  $autoFaelle=@(
    @(5,5,$true,$true,'A',@('A'),'unveraendert'),
    @(5,6,$false,$false,'',@('A'),'keinbild'),
    @(5,6,$true,$false,'B',@('A'),'keinScreenshot'),
    @(5,6,$true,$true,'A',@('A'),'bekanntesBild'),
    @(5,6,$true,$true,'A',@('A','B'),'bekanntesBild'),
    @(5,6,$true,$true,'C',@('A','B'),'lesen'),
    @(5,6,$true,$true,'',@(),'lesen')
  )
  foreach ($fall in $autoFaelle) {
    $urteil=Get-AutomatikEntscheidung ($fall[0]) ($fall[1]) ($fall[2]) ($fall[3]) ($fall[4]) ([string[]]$fall[5])
    if ($urteil -ne $fall[6]) { Write-Output ('Automatik-Regel falsch bei '+$fall[0]+'/'+$fall[1]+'/'+$fall[4]+': '+$urteil); exit 1 }
  }
  for ($i=0;$i -lt 35;$i++) { Add-BekanntesBild ('K'+$i) }
  Add-BekanntesBild 'K34'
  if ($script:bekannteBilder.Count -ne 30 -or $script:bekannteBilder.Contains('K0') -or -not $script:bekannteBilder.Contains('K34')) { Write-Output 'Bildgedaechtnis haelt nicht die letzten 30'; exit 1 }
  $script:bekannteBilder.Clear()
  Write-Output 'Automatik-Regeln: ok'
  $bmp=[System.Drawing.Bitmap]::new(1000,150); $g=[System.Drawing.Graphics]::FromImage($bmp); $g.Clear([System.Drawing.Color]::White)
  $font=[System.Drawing.Font]::new('Arial',32); $g.DrawString('This is a screenshot reading test.',$font,[System.Drawing.Brushes]::Black,10,30); $g.Dispose(); $font.Dispose()
  $result=Read-Image $bmp 'en-US'; $bmp.Dispose()
  $speech=[System.Speech.Synthesis.SpeechSynthesizer]::new(); $out=[System.IO.MemoryStream]::new(); $speech.SetOutputToWaveStream($out); $speech.Speak('Test.'); $size=$out.Length; $speech.Dispose(); $out.Dispose()
  Write-Output "OCR: $result"; Write-Output "Audio bytes: $size"; if ($result -notmatch 'screenshot reading test' -or $size -lt 1000) { exit 1 }; exit 0
}
$form=New-Object System.Windows.Forms.Form; $form.Text='ShotReader'; $form.Width=660; $form.Height=542; $form.StartPosition='CenterScreen'
$form.BackColor=[System.Drawing.Color]::FromArgb(30,31,36); $form.ForeColor=[System.Drawing.Color]::White
$tip=New-Object System.Windows.Forms.Label; $tip.Text='Screenshot kopieren und hier mit Strg+V einfuegen. Text pruefen, dann Klaus starten.'; $tip.SetBounds(15,12,610,30); $form.Controls.Add($tip)
$tempoLabel=New-Object System.Windows.Forms.Label; $tempoLabel.Text=('Tempo: {0:N2}x' -f 1.0); $tempoLabel.SetBounds(15,50,110,26); $form.Controls.Add($tempoLabel)
$tempo=New-Object System.Windows.Forms.TrackBar; $tempo.Minimum=4; $tempo.Maximum=12; $tempo.Value=4; $tempo.TickFrequency=1; $tempo.SmallChange=1; $tempo.LargeChange=1; $tempo.BackColor=$form.BackColor; $tempo.SetBounds(130,44,495,45); $tempo.Anchor='Top,Left,Right'; $form.Controls.Add($tempo)
$lang=New-Object System.Windows.Forms.ComboBox; $lang.DropDownStyle='DropDownList'; $lang.Items.AddRange(@('Deutsch','English')); $lang.SelectedIndex=0; $lang.SetBounds(15,92,110,32); $form.Controls.Add($lang)
$paste=New-Object System.Windows.Forms.Button; $paste.Text='Einfuegen (Strg+V)'; $paste.SetBounds(135,92,140,32); $form.Controls.Add($paste)
$read=New-Object System.Windows.Forms.Button; $read.Text='Klaus vorlesen'; $read.SetBounds(285,92,130,32); $form.Controls.Add($read)
$pause=New-Object System.Windows.Forms.Button; $pause.Text='Pause'; $pause.SetBounds(425,92,95,32); $pause.Enabled=$false; $form.Controls.Add($pause)
$stop=New-Object System.Windows.Forms.Button; $stop.Text='Stopp'; $stop.SetBounds(530,92,95,32); $form.Controls.Add($stop)

foreach ($button in @($paste, $read, $pause, $stop)) {
  $button.UseVisualStyleBackColor=$false
  $button.FlatStyle=[System.Windows.Forms.FlatStyle]::Flat
  $button.BackColor=[System.Drawing.Color]::FromArgb(235,239,245)
  $button.ForeColor=[System.Drawing.Color]::FromArgb(19,26,38)
  $button.FlatAppearance.BorderColor=[System.Drawing.Color]::FromArgb(150,165,185)
  $button.FlatAppearance.MouseOverBackColor=[System.Drawing.Color]::FromArgb(211,222,238)
  $button.FlatAppearance.MouseDownBackColor=[System.Drawing.Color]::FromArgb(190,207,229)
  $button.Font=New-Object System.Drawing.Font('Segoe UI',9,[System.Drawing.FontStyle]::Bold)
}
$lang.BackColor=[System.Drawing.Color]::FromArgb(235,239,245); $lang.ForeColor=[System.Drawing.Color]::FromArgb(19,26,38)
$status=New-Object System.Windows.Forms.Label; $status.Text='OCR lokal. Vorlesen: Text gestreamt ueber OpenRouter / Microsoft.'; $status.SetBounds(15,134,610,28); $form.Controls.Add($status)
$auto=New-Object System.Windows.Forms.CheckBox; $auto.Text='Automatisch vorlesen (neue Screenshots)'; $auto.SetBounds(15,162,420,26); $auto.ForeColor=[System.Drawing.Color]::White; $auto.BackColor=$form.BackColor; $auto.Checked=$false; $form.Controls.Add($auto)
$text=New-Object System.Windows.Forms.TextBox; $text.Multiline=$true; $text.ScrollBars='Vertical'; $text.SetBounds(15,192,610,292); $text.Anchor='Top,Bottom,Left,Right'; $text.BackColor=[System.Drawing.Color]::FromArgb(45,46,52); $text.ForeColor=[System.Drawing.Color]::White; $text.Font=New-Object System.Drawing.Font('Segoe UI',11); $form.Controls.Add($text)
$form.KeyPreview=$true

if (-not ('ScreenshotClipboard.Sequence' -as [type])) {
  Add-Type -TypeDefinition 'namespace ScreenshotClipboard { public static class Sequence { [System.Runtime.InteropServices.DllImport("user32.dll")] public static extern uint GetClipboardSequenceNumber(); } }'
}
$script:lastClipboardSequence=[ScreenshotClipboard.Sequence]::GetClipboardSequenceNumber()
$script:clipboardBusy=$false

$script:player=New-Object -ComObject WMPlayer.OCX
$script:job=$null
$script:audio=$null
$script:sessionDir=$null
$script:stdoutTask=$null
$script:chunkCount=0
$script:jobFinished=$false

function Stop-Playback {
  if ($script:job -and -not $script:job.HasExited) {
    try { $script:job.Kill() } catch {}
  }
  if ($script:job) {
    try { $script:job.Dispose() } catch {}
    $script:job=$null
  }
  $script:stdoutTask=$null
  $timer.Stop()
  $read.Enabled=$true
  $pause.Text='Pause'
  $pause.Enabled=$false
  try {
    $script:player.controls.stop()
    $script:player.currentPlaylist.clear()
    $script:player.close()
  } catch {}
}

function Cleanup-Audio {
  Stop-Playback
  if ($script:audio -and (Test-Path $script:audio)) {
    Remove-Item $script:audio -Force -ErrorAction SilentlyContinue
  }
  if ($script:sessionDir -and (Test-Path $script:sessionDir)) {
    Remove-Item $script:sessionDir -Recurse -Force -ErrorAction SilentlyContinue
  }
  $script:audio=$null
  $script:sessionDir=$null
}

$timer=New-Object System.Windows.Forms.Timer; $timer.Interval=100
$timer.Add_Tick({
  while ($script:stdoutTask -and $script:stdoutTask.IsCompleted) {
    $line=$script:stdoutTask.Result
    if ($line -eq $null) { break }
    if ($line.StartsWith('CHUNK:')) {
      $chunkPath=$line.Substring(6).Trim()
      if (Test-Path $chunkPath) {
        $script:chunkCount++
        $media=$script:player.newMedia($chunkPath)
        $script:player.currentPlaylist.appendItem($media)
        Apply-Tempo
        if ($script:player.playState -ne 3 -and $script:player.playState -ne 6 -and $script:player.playState -ne 2) {
          $script:player.controls.play()
        }
        $status.Text="Klaus liest vor (Abschnitt $($script:chunkCount)) ..."
      }
    }
    $script:stdoutTask=$script:job.StandardOutput.ReadLineAsync()
  }

  if ($script:job -and $script:job.HasExited) {
    if ($script:job.ExitCode -ne 0) {
      $detail=$script:job.StandardError.ReadToEnd()
      Stop-Playback
      $status.Text='Vorlesen fehlgeschlagen: ' + $detail.Substring(0, [Math]::Min(250, $detail.Length))
      return
    }
    $script:jobFinished=$true
  }

  if ($script:jobFinished) {
    $isPlaying=($script:player.playState -eq 3 -or $script:player.playState -eq 6 -or $script:player.playState -eq 9 -or $script:player.playState -eq 2)
    if (-not $isPlaying) {
      $timer.Stop()
      $read.Enabled=$true
      $pause.Enabled=$false
      $pause.Text='Pause'
      if ($script:chunkCount -gt 0) {
        $status.Text='Vorlesen abgeschlossen.'
      }
      if ($script:job) {
        $script:job.Dispose()
        $script:job=$null
      }
    }
  }
})

function Paste-Content {
  try {
    if ([System.Windows.Forms.Clipboard]::ContainsImage()) {
      $status.Text='Erkenne Screenshot lokal ...'; $form.Refresh()
      $image=[System.Windows.Forms.Clipboard]::GetImage()
      try { Add-BekanntesBild (Get-BildKennung $image); $value=Read-Image $image $(if($lang.SelectedIndex -eq 0){'de-DE'}else{'en-US'}) } finally { $image.Dispose() }
    } elseif ([System.Windows.Forms.Clipboard]::ContainsText()) { $value=[System.Windows.Forms.Clipboard]::GetText() }
    else { throw 'Kein Bild oder Text in der Zwischenablage.' }
    if ([string]::IsNullOrWhiteSpace($value)) { throw 'Kein Text erkannt. Ausschnitt erneut aufnehmen.' }
    $text.Text=$value; $status.Text='Eingefuegt. Text pruefen und auf Klaus vorlesen klicken.'
    return $true
  } catch { $status.Text='Einfuegen fehlgeschlagen: '+$_.Exception.Message; return $false }
}

$script:fileFactor=1.0
function Get-Speed { return $tempo.Value*0.25 }
function Apply-Tempo {
  try {
    $rate=Get-PlayerRate (Get-Speed) $script:fileFactor
    if ([Math]::Abs($script:player.settings.rate-$rate) -gt 0.001) { $script:player.settings.rate=$rate }
  } catch {}
}
$tempo.Add_ValueChanged({
  $speed=Get-Speed
  $tempoLabel.Text=('Tempo: {0:N2}x' -f $speed)
  Apply-Tempo
  if ($script:job -and $speed -gt (2*$script:fileFactor)) { $status.Text='Ueber 2x gilt ab dem naechsten Klaus-Start.' }
})

$paste.Add_Click({ Paste-Content })
$form.Add_KeyDown({ param($sender,$e) if ($e.Control -and $e.KeyCode -eq [System.Windows.Forms.Keys]::V) { $e.SuppressKeyPress=$true; Paste-Content } })

$read.Add_Click({
  try {
    if ([string]::IsNullOrWhiteSpace($text.Text)) { throw 'Bitte zuerst einen Screenshot oder Text einfuegen.' }
    Cleanup-Audio
    $script:fileFactor=Get-FileFactor (Get-Speed)
    Apply-Tempo
    $stem='klaus-'+[guid]::NewGuid().ToString()
    $scratchDir=Join-Path $env:LOCALAPPDATA 'hermes\cache\scratch'
    if (-not (Test-Path $scratchDir)) { [void](New-Item -ItemType Directory -Path $scratchDir -Force) }
    $script:audio=Join-Path $scratchDir ($stem+'.mp3')
    $script:sessionDir=Join-Path $scratchDir ('session_'+$stem)

    $psi=New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    $helper=Join-Path $env:LOCALAPPDATA 'hermes\werkzeuge\shotreader_tts.py'
    $psi.Arguments='"'+$helper+'" "'+$script:audio+'"'
    if ($script:fileFactor -ne 1.0) { $psi.Arguments+=' --tempo 1.5' }
    $psi.UseShellExecute=$false
    $psi.CreateNoWindow=$true
    $psi.RedirectStandardInput=$true
    $psi.RedirectStandardOutput=$true
    $psi.RedirectStandardError=$true
    $psi.StandardOutputEncoding=[System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding=[System.Text.Encoding]::UTF8

    $script:job=[System.Diagnostics.Process]::Start($psi)
    $bytes=[System.Text.Encoding]::UTF8.GetBytes($text.Text)
    $script:job.StandardInput.BaseStream.Write($bytes,0,$bytes.Length)
    $script:job.StandardInput.Close()

    $script:stdoutTask=$script:job.StandardOutput.ReadLineAsync()
    $script:chunkCount=0
    $script:jobFinished=$false
    $read.Enabled=$false
    $pause.Enabled=$true
    $pause.Text='Pause'
    $status.Text='Klaus generiert Sprache (Abschnitte werden sofort gestreamt) ...'
    $timer.Interval=100
    $timer.Start()
  } catch {
    $read.Enabled=$true
    $pause.Enabled=$false
    $status.Text='Vorlesen fehlgeschlagen: '+$_.Exception.Message
  }
})

$pause.Add_Click({
  if ($script:player.playState -eq 3) {
    $script:player.controls.pause()
    $pause.Text='Weiter'
    $status.Text='Vorlesen pausiert.'
  } elseif ($script:player.playState -eq 2) {
    $script:player.controls.play()
    $pause.Text='Pause'
    $status.Text="Klaus liest vor (Abschnitt $($script:chunkCount)) ..."
  }
})

$stop.Add_Click({
  Stop-Playback
  $status.Text='Vorlesen gestoppt.'
})

$watch=New-Object System.Windows.Forms.Timer; $watch.Interval=700
$auto.Add_CheckedChanged({
  $script:lastClipboardSequence=[ScreenshotClipboard.Sequence]::GetClipboardSequenceNumber()
  if ($auto.Checked) {
    # Was beim Einschalten schon in der Zwischenablage liegt, gilt als alt -
    # vorgelesen werden nur NEUE Bildinhalte.
    $vorhandeneKennung=''
    try {
      if ([System.Windows.Forms.Clipboard]::ContainsImage()) {
        $vorhandenesBild=[System.Windows.Forms.Clipboard]::GetImage()
        try { $vorhandeneKennung=Get-BildKennung $vorhandenesBild } finally { $vorhandenesBild.Dispose() }
      }
    } catch {}
    Add-BekanntesBild $vorhandeneKennung
    Write-Protokoll 'Automatik an'
    $status.Text='Automatik an: neue Screenshots werden sofort erkannt und vorgelesen.'
    $watch.Start()
  }
  else { $watch.Stop(); $status.Text='Automatik aus. Manuelles Einfuegen und Vorlesen verfuegbar.' }
})

$watch.Add_Tick({
  if (-not $auto.Checked -or $script:clipboardBusy) { return }
  $sequence=[ScreenshotClipboard.Sequence]::GetClipboardSequenceNumber()
  if ($sequence -eq $script:lastClipboardSequence) { return }
  try {
    $alt=$script:lastClipboardSequence
    $hatBild=[System.Windows.Forms.Clipboard]::ContainsImage()
    $formate=@()
    $objekt=[System.Windows.Forms.Clipboard]::GetDataObject()
    if ($objekt) { $formate=@($objekt.GetFormats($false)) }
    $nurBild=Test-NurBild $formate
    $kennung=''
    if ($hatBild -and $nurBild) {
      $bild=[System.Windows.Forms.Clipboard]::GetImage()
      try { $kennung=Get-BildKennung $bild } finally { $bild.Dispose() }
    }
    $script:lastClipboardSequence=$sequence
    $entscheidung=Get-AutomatikEntscheidung ([long]$alt) ([long]$sequence) $hatBild $nurBild $kennung ([string[]]$script:bekannteBilder.ToArray())
    $kurz=if ($kennung) { $kennung.Substring(0,11) } else { '-' }
    Write-Protokoll ("Sequenz $sequence | $entscheidung | Kennung $kurz | Formate "+($formate -join ', '))
    if ($entscheidung -eq 'lesen') {
      $script:clipboardBusy=$true
      Stop-Playback
      if (Paste-Content) { $read.PerformClick() }
    } elseif ($entscheidung -eq 'bekanntesBild') {
      # Kommt derselbe Inhalt zurueck (typeFREE stellt nach dem Einfuegen den
      # Vorinhalt wieder her), wird NICHT erneut vorgelesen - und kein Stopp.
      if ($script:player.playState -ne 3 -and $script:player.playState -ne 6) {
        $status.Text='Derselbe Screenshot liegt wieder in der Zwischenablage - nicht erneut vorgelesen.'
      }
    }
  } catch { $status.Text='Zwischenablage momentan nicht lesbar: '+$_.Exception.Message }
  finally { $script:clipboardBusy=$false }
})

$form.Add_FormClosed({
  $watch.Stop()
  Cleanup-Audio
})

# -AutoStart startet mit sofort aktiver Automatik (fuer Prueflaeufe).
if ($AutoStart) { $auto.Checked=$true }

[void]$form.ShowDialog()
