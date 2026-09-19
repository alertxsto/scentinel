$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$version = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "==> packaging Scentinel $version"

python -m pip install --upgrade pip
python -m pip install ".[cfd,report]" pyinstaller

New-Item -ItemType Directory -Force -Path dist/packages | Out-Null
python -m PyInstaller --noconfirm --clean packaging/scentinel.spec

$exe = "dist/Scentinel.exe"
if (-not (Test-Path $exe)) { throw "PyInstaller did not produce $exe" }
Copy-Item $exe "dist/packages/Scentinel-$version.exe"
Get-Item "dist/packages/Scentinel-$version.exe"
