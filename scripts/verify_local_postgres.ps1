param(
    [string]$ServerHost = '127.0.0.1',
    [int]$Port = 5432,
    [string]$User = 'postgres',
    [string]$Database = 'postgres'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Resolve-Psql.ps1')

$psql = Resolve-PsqlPath

Write-Host ('Connecting to PostgreSQL ' + $ServerHost + ':' + $Port + '/' + $Database + '. Enter the password only at the psql prompt.')
& $psql -h $ServerHost -p $Port -U $User -d $Database -W -c 'SELECT current_user, current_database(), version();'
if ($LASTEXITCODE -ne 0) {
    throw ('PostgreSQL verification failed. Exit code: ' + $LASTEXITCODE)
}
