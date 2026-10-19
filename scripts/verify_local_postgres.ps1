param(
    [string]$ServerHost = '127.0.0.1',
    [int]$Port = 5432,
    [string]$User = 'postgres',
    [string]$Database = 'postgres'
)

$psql = 'D:\LenovoSoftstore\Install\PostgreSQL\bin\psql.exe'
if (-not (Test-Path -LiteralPath $psql)) {
    throw ('psql not found: ' + $psql)
}

Write-Host ('Connecting to PostgreSQL ' + $ServerHost + ':' + $Port + '/' + $Database + '. Enter the password only at the psql prompt.')
& $psql -h $ServerHost -p $Port -U $User -d $Database -W -c 'SELECT current_user, current_database(), version();'
if ($LASTEXITCODE -ne 0) {
    throw ('PostgreSQL verification failed. Exit code: ' + $LASTEXITCODE)
}
