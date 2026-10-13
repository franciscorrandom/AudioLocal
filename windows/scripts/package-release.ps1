$ErrorActionPreference = 'Stop'
$BuildRoot = Split-Path -Parent $PSScriptRoot
Set-Location $BuildRoot
New-Item -ItemType Directory -Force release, release-stage | Out-Null
$name = 'AudioLocal-1.0.0-beta.1-Windows-x64'
$stage = Join-Path 'release-stage' $name
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item 'dist/AudioLocal/*' $stage -Recurse
Copy-Item 'README.txt' $stage
Compress-Archive -Path $stage -DestinationPath "release/$name.zip" -CompressionLevel Optimal -Force
$compiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (!(Test-Path $compiler)) { throw 'The runner must include Inno Setup 6; no unverified installer download is performed' }
& $compiler 'AudioLocal.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
# A narrow source archive provides app source, dependency source, build scripts and licenses.
$sourceStage = 'release-stage/AudioLocal-1.0.0-beta.1-Windows-Fuentes'
New-Item -ItemType Directory -Force $sourceStage | Out-Null
foreach ($item in @('src','scripts','licenses','fixtures','Windows.spec','windows-version.txt','AudioLocal.iss','requirements-build.lock','BUILD.md','README.txt')) {
    Copy-Item $item $sourceStage -Recurse
}
Get-ChildItem "$sourceStage/src" -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force "$sourceStage/dependency-source" | Out-Null
foreach ($item in @('ffmpeg-7.1.tar.xz','lame-3.100.tar.gz','mutagen-1.47.0.tar.gz','yt-dlp-2026.08.19.tar.gz')) {
    Copy-Item "build-sources/$item" "$sourceStage/dependency-source"
}
Copy-Item 'build-sources/ffmpeg-7.1/config.h' "$sourceStage/dependency-source/ffmpeg-windows-config.h"
Copy-Item 'build-sources/ffmpeg-7.1/ffbuild/config.mak' "$sourceStage/dependency-source/ffmpeg-windows-config.mak"
Copy-Item 'build-sources/audio-libs/lib/libmp3lame.a' "$sourceStage/dependency-source"
Compress-Archive -Path $sourceStage -DestinationPath 'release/AudioLocal-1.0.0-beta.1-Windows-Fuentes.zip' -CompressionLevel Optimal -Force
$manifest = @()
foreach ($file in Get-ChildItem 'release' -File | Where-Object { $_.Extension -in @('.zip','.exe') }) {
    $manifest += @{name=$file.Name; bytes=$file.Length; sha256=(Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content 'release/release-manifest.json' -Encoding utf8
$manifest | ForEach-Object { "$($_.sha256)  $($_.name)" } | Set-Content 'release/SHA256SUMS.txt' -Encoding ascii
