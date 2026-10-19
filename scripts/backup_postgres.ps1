param(
  [string]$Output = "./backups/pricing-$(Get-Date -Format yyyyMMdd-HHmmss).dump"
)

$root = Split-Path -Parent $PSScriptRoot
$outputPath = [IO.Path]::GetFullPath((Join-Path $root $Output))
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outputPath) | Out-Null

$psi = [Diagnostics.ProcessStartInfo]::new()
$psi.FileName = 'docker'
$psi.Arguments = 'compose exec -T db pg_dump -U pricing -d pricing -Fc'
$psi.WorkingDirectory = $root
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$process = [Diagnostics.Process]::new()
$process.StartInfo = $psi
[void]$process.Start()
$stream = [IO.File]::Create($outputPath)
try { $process.StandardOutput.BaseStream.CopyTo($stream) } finally { $stream.Dispose() }
$process.WaitForExit()
if ($process.ExitCode -ne 0) {
  Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
  throw "docker pg_dump failed with exit code $($process.ExitCode)"
}
Write-Host "Backup written to $outputPath"

