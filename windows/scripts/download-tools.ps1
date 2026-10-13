$ErrorActionPreference = 'Stop'
$BuildRoot = Split-Path -Parent $PSScriptRoot
Set-Location $BuildRoot
New-Item -ItemType Directory -Force tools, build-sources, verification | Out-Null
function Get-VerifiedFile([string]$Url, [string]$Destination, [string]$Sha256) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try { Invoke-WebRequest -Uri $Url -OutFile $Destination -MaximumRedirection 10; break }
        catch { if ($attempt -eq 3) { throw }; Start-Sleep -Seconds (2 * $attempt) }
    }
    $actual = (Get-FileHash -Algorithm SHA256 $Destination).Hash.ToLowerInvariant()
    if ($actual -ne $Sha256) { throw "Hash mismatch: $Destination" }
}
Get-VerifiedFile 'https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp.exe' 'tools/yt-dlp.exe' '66674953fe251b89f4d08c5f0e35e0728679bd67ab3d7d05c0562af101dd3e7a'
Get-VerifiedFile 'https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp.tar.gz' 'build-sources/yt-dlp-2026.08.19.tar.gz' '072aad4f2a7604e92155f61a275a4752dc64046c8f6d90df3710525d94cd37c1'
Get-VerifiedFile 'https://nodejs.org/dist/v24.14.1/node-v24.14.1-win-x64.zip' 'build-sources/node-v24.14.1-win-x64.zip' '6e50ce5498c0cebc20fd39ab3ff5df836ed2f8a31aa093cecad8497cff126d70'
Expand-Archive -Path 'build-sources/node-v24.14.1-win-x64.zip' -DestinationPath build-sources -Force
Copy-Item 'build-sources/node-v24.14.1-win-x64/node.exe' 'tools/node.exe'
Copy-Item 'build-sources/node-v24.14.1-win-x64/LICENSE' 'licenses/Node-LICENSE.txt'
Get-VerifiedFile 'https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz' 'build-sources/ffmpeg-7.1.tar.xz' '40973d44970dbc83ef302b0609f2e74982be2d85916dd2ee7472d30678a7abe6'
Get-VerifiedFile 'https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz' 'build-sources/lame-3.100.tar.gz' 'ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e'
# Corresponding source of GPL Mutagen included by the official yt-dlp executable.
Get-VerifiedFile 'https://files.pythonhosted.org/packages/source/m/mutagen/mutagen-1.47.0.tar.gz' 'build-sources/mutagen-1.47.0.tar.gz' '719fadef0a978c31b4cf3c956261b3c58b6948b32023078a2117b1de09f0fc99'
Write-Output 'Official Windows tools and corresponding source verified.'
