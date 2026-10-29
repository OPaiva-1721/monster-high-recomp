$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$packPython = Join-Path $repo 'build/packaging-venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $packPython)) {
    python -m venv (Join-Path $repo 'build/packaging-venv')
    if ($LASTEXITCODE) { throw 'Falha ao criar ambiente de empacotamento.' }
}
& $packPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
if ($LASTEXITCODE) { throw 'Falha ao preparar empacotador.' }
& $packPython (Join-Path $PSScriptRoot 'package.py')
if ($LASTEXITCODE) { throw 'Falha no pacote.' }
