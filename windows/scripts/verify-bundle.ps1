$ErrorActionPreference = 'Stop'
$BuildRoot = Split-Path -Parent $PSScriptRoot
$ReportDirectory = Join-Path $BuildRoot 'verification'
New-Item -ItemType Directory -Force $ReportDirectory | Out-Null
$exe = Join-Path $BuildRoot 'dist/AudioLocal/AudioLocal.exe'
$report = Join-Path $ReportDirectory 'windows-packaged-verification.json'
$fixtures = Join-Path $BuildRoot 'fixtures'
$arguments = '--verify-package "' + $report + '" --fixtures "' + $fixtures + '"'
$previousPath = $env:PATH
try {
    # This simulates a user without Python, Node, FFmpeg or build tools in PATH.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
    $deadline = (Get-Date).AddSeconds(90)
    $ready = Join-Path $ReportDirectory 'gui-ready.json'
    while (!(Test-Path $ready) -and !(Test-Path $report)) {
        if ($process.HasExited) { break }
        if ((Get-Date) -gt $deadline) { Stop-Process -Id $process.Id -Force; throw 'Packaged verification timed out' }
        Start-Sleep -Milliseconds 250
    }
    if (Test-Path $ready) {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        Start-Sleep -Milliseconds 300
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $bitmap.Save((Join-Path $ReportDirectory 'windows-packaged-gui.png'), [System.Drawing.Imaging.ImageFormat]::Png)
        $graphics.Dispose()
        $bitmap.Dispose()
    }
    if (!$process.WaitForExit(30000)) { Stop-Process -Id $process.Id -Force; throw 'Packaged GUI did not close' }
    if (!(Test-Path $report)) { throw 'Packaged executable did not produce a verification report' }
    $result = Get-Content $report -Raw | ConvertFrom-Json
    if (!$result.passed) { throw ($result.error | Out-String) }
    Write-Output ($result | ConvertTo-Json -Depth 12)
} finally { $env:PATH = $previousPath }
