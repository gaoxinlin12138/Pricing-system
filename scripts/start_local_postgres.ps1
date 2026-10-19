param(
    [string]$ServerHost = '127.0.0.1',
    [int]$Port = 5432,
    [string]$DbUser = 'postgres',
    [string]$Database = 'pricing',
    [int]$AppPort = 8001
)

$ErrorActionPreference = 'Stop'
$securePassword = Read-Host 'PostgreSQL password (input is hidden)' -AsSecureString
$passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
$oldDatabaseUrl = $env:DATABASE_URL
$oldSessionSecret = $env:SESSION_SECRET
try {
    $encodedPassword = [uri]::EscapeDataString($plainPassword)
    $env:DATABASE_URL = ('postgresql+psycopg://' + $DbUser + ':' + $encodedPassword + '@' + $ServerHost + ':' + $Port + '/' + $Database)
    if (-not $env:SESSION_SECRET) { $env:SESSION_SECRET = 'local-development-change-me' }
    Push-Location (Join-Path $PSScriptRoot '..\backend')
    try {
        Write-Host ('Starting backend on http://127.0.0.1:' + $AppPort + ' using PostgreSQL database ' + $Database)
        py -m uvicorn main:app --host 127.0.0.1 --port $AppPort
    } finally {
        Pop-Location
    }
} finally {
    if ($null -eq $oldDatabaseUrl) { Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue } else { $env:DATABASE_URL = $oldDatabaseUrl }
    if ($null -eq $oldSessionSecret) { Remove-Item Env:SESSION_SECRET -ErrorAction SilentlyContinue } else { $env:SESSION_SECRET = $oldSessionSecret }
    $plainPassword = $null
}
