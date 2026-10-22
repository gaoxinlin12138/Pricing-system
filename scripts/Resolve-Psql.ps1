# Shared helpers for the local PostgreSQL scripts.

function Resolve-PsqlPath {
    $candidates = New-Object System.Collections.Generic.List[string]

    $command = Get-Command psql.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source) { $candidates.Add($command.Source) }

    foreach ($key in @('HKLM:\SOFTWARE\PostgreSQL\Installations', 'HKLM:\SOFTWARE\WOW6432Node\PostgreSQL\Installations')) {
        if (Test-Path $key) {
            Get-ChildItem $key -ErrorAction SilentlyContinue | ForEach-Object {
                $base = (Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue).'Base Directory'
                if ($base) { $candidates.Add((Join-Path $base 'bin\psql.exe')) }
            }
        }
    }

    Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'postgresql*' -and $_.PathName -match '"?([A-Za-z]:\\[^"]*?)\\bin\\' } |
        ForEach-Object { $candidates.Add((Join-Path $matches[1] 'bin\psql.exe')) }

    foreach ($root in @(
        'C:\Program Files\PostgreSQL',
        'E:\software\PostgreSQL',
        'D:\Program Files\PostgreSQL',
        'D:\LenovoSoftstore\Install\PostgreSQL'
    )) {
        if (Test-Path $root) {
            Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | ForEach-Object {
                $candidates.Add((Join-Path $_.FullName 'bin\psql.exe'))
            }
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    throw 'psql not found. Install PostgreSQL client tools or add psql.exe to PATH.'
}

function Resolve-BackendPython {
    $venv = Join-Path $PSScriptRoot '..\backend\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venv) { return $venv }
    return 'py'
}
