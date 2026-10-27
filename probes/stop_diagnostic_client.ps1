param(
    [Parameter(Mandatory=$true)][int]$DiagnosticPid,
    [Parameter(Mandatory=$true)][string]$StartedAfter,
    [long]$VerifiedWindowHandle = 0,
    [string]$ExpectedCreationDate = '',
    [Parameter(Mandatory=$true)][string]$ResultPath
)
$ErrorActionPreference = 'Stop'
$report = @{ pid = $DiagnosticPid; status = 'checking'; time = (Get-Date).ToString('o') }
try {
    $target = Get-Process -Id $DiagnosticPid -ErrorAction SilentlyContinue
    if ($null -eq $target) {
        $report.status = 'already_closed'
    } else {
        $expectedPath = 'F:\roe\32838\Europa_Client.exe'
        $actualPath = $target.Path
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$DiagnosticPid"
        if ($processInfo.Name -ne 'Europa_Client.exe') { throw 'Process name differs' }
        if ($actualPath -and $actualPath -ne $expectedPath) { throw 'Executable path differs from the diagnostic client' }
        if (-not $actualPath) {
            # Fallback requires a fresh CUA window identified by the full game
            # path, its exact owning PID, and the observed process creation time.
            if (-not $VerifiedWindowHandle -or -not $ExpectedCreationDate) { throw 'No independent window identity supplied' }
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class RoeDiagnosticWindowOwner {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
}
'@
            [uint32]$windowProcess = 0
            $threadId = [RoeDiagnosticWindowOwner]::GetWindowThreadProcessId([IntPtr]$VerifiedWindowHandle, [ref]$windowProcess)
            if (-not $threadId -or $windowProcess -ne $DiagnosticPid) { throw 'Window no longer belongs to the diagnostic process' }
            $observed = ([DateTimeOffset]$processInfo.CreationDate).UtcDateTime
            $expected = [DateTimeOffset]::Parse($ExpectedCreationDate).UtcDateTime
            if ([Math]::Abs(($observed - $expected).TotalMilliseconds) -gt 1) { throw 'Process creation time changed' }
            $report.identity = 'CUA full-path window + exact owning PID + creation time'
        }
        if ($processInfo.CreationDate -lt [DateTimeOffset]::Parse($StartedAfter).LocalDateTime) {
            throw 'Process started before this diagnostic run'
        }
        $report.path = if ($actualPath) { $actualPath } else { $expectedPath }
        $report.started = $processInfo.CreationDate.ToString('o')
        Stop-Process -InputObject $target -Force
        $target.WaitForExit(5000) | Out-Null
        $report.status = if (Get-Process -Id $DiagnosticPid -ErrorAction SilentlyContinue) { 'still_running' } else { 'closed' }
    }
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
}
$report | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8
