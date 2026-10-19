param(
    [string]$ServerHost = '127.0.0.1',
    [int]$Port = 5432,
    [string]$DbUser = 'postgres',
    [string]$Database = 'pricing'
)

$ErrorActionPreference = 'Stop'
$psql = 'D:\LenovoSoftstore\Install\PostgreSQL\bin\psql.exe'
if (-not (Test-Path -LiteralPath $psql)) {
    throw ('psql not found: ' + $psql)
}

$securePassword = Read-Host 'PostgreSQL password (input is hidden)' -AsSecureString
$passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)

$oldPassword = $env:PGPASSWORD
$oldDatabaseUrl = $env:DATABASE_URL
try {
    $env:PGPASSWORD = $plainPassword
    $queryOutput = @(& $psql -h $ServerHost -p $Port -U $DbUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$Database';")
    $exists = (($queryOutput -join "`n").Trim())
    if ($LASTEXITCODE -ne 0) {
        throw ('Cannot query PostgreSQL. Exit code: ' + $LASTEXITCODE)
    }
    if ($exists -ne '1') {
        Write-Host ('Creating database ' + $Database + '...')
        & $psql -h $ServerHost -p $Port -U $DbUser -d postgres -c ('CREATE DATABASE "' + $Database + '";')
        if ($LASTEXITCODE -ne 0) {
            throw ('Database creation failed. Exit code: ' + $LASTEXITCODE)
        }
    } else {
        Write-Host ('Database ' + $Database + ' already exists.')
    }

    # psycopg does not consistently consume PGPASSWORD through SQLAlchemy on all
    # Windows installations, so pass an URL-encoded password for this process only.
    $encodedPassword = [uri]::EscapeDataString($plainPassword)
    $env:DATABASE_URL = ('postgresql+psycopg://' + $DbUser + ':' + $encodedPassword + '@' + $ServerHost + ':' + $Port + '/' + $Database)
    Push-Location (Join-Path $PSScriptRoot '..\backend')
    try {
        py -m alembic -c alembic.ini upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw ('Alembic migration failed. Exit code: ' + $LASTEXITCODE)
        }
    } finally {
        Pop-Location
    }
    Write-Host 'PostgreSQL database is ready and migrations are complete.'
} finally {
    if ($null -eq $oldPassword) { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue } else { $env:PGPASSWORD = $oldPassword }
    if ($null -eq $oldDatabaseUrl) { Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue } else { $env:DATABASE_URL = $oldDatabaseUrl }
    $plainPassword = $null
}
