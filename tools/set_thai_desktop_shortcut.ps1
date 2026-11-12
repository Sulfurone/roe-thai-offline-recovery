param([string]$Name = 'ROE')

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Name) -or $Name.Length -gt 64 -or $Name -match '[\\/:*?"<>|]') {
    throw 'Choose a single desktop shortcut name without path characters.'
}
$workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$launcher = Join-Path $workspace 'start_ingame_control.cmd'
$oldLauncher = Join-Path $workspace 'start_native_lobby.cmd'
$commandProcessor = Join-Path ([Environment]::SystemDirectory) 'cmd.exe'
$oldArguments = '/d /s /c ""' + $launcher + '""'
$desktopLauncher = Join-Path $PSScriptRoot 'launch_thai_desktop.pyw'
$launcherArguments = '"' + $desktopLauncher + '"'
if (!(Test-Path -LiteralPath $launcher -PathType Leaf) -or !(Test-Path -LiteralPath $desktopLauncher -PathType Leaf)) {
    throw 'The Thai daytime/parachute launcher is missing.'
}
$pathPython = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
$bundledPython = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$python = @($env:ROE_PYTHON, $bundledPython, $pathPython) | Where-Object {
    $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $_) 'pythonw.exe') -PathType Leaf)
} | Select-Object -First 1
if (!$python) { throw 'Set ROE_PYTHON to an installed Python executable with pythonw.exe in the same directory.' }
$pythonWindowless = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutPath = Join-Path $desktop ($Name + '.lnk')
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
if (Test-Path -LiteralPath $shortcutPath) {
    $legacyTarget = @($launcher, $oldLauncher) | Where-Object {
        [StringComparer]::OrdinalIgnoreCase.Equals($_, $shortcut.TargetPath)
    }
    $legacyCommand = [StringComparer]::OrdinalIgnoreCase.Equals($commandProcessor, $shortcut.TargetPath) -and
        [StringComparer]::OrdinalIgnoreCase.Equals($oldArguments, $shortcut.Arguments)
    $knownDesktopLauncher = [IO.Path]::GetFileName($shortcut.TargetPath) -ieq 'pythonw.exe' -and
        [StringComparer]::OrdinalIgnoreCase.Equals($launcherArguments, $shortcut.Arguments)
    if (!$knownDesktopLauncher -and !$legacyCommand -and (!$legacyTarget -or $shortcut.Arguments)) {
        throw 'Existing shortcut points elsewhere. Choose another name; unrelated or Steam shortcuts are preserved.'
    }
    if ($knownDesktopLauncher -and $shortcut.WindowStyle -eq 1 -and
            [StringComparer]::OrdinalIgnoreCase.Equals($shortcut.TargetPath, $pythonWindowless) -and
            [StringComparer]::OrdinalIgnoreCase.Equals($shortcut.WorkingDirectory, $workspace)) {
        Write-Output "Already points to the Thai parachute/menu launcher: $shortcutPath"
        return
    }
    $backupFolder = Join-Path $workspace 'private/launcher-shortcuts'
    New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null
    $backupPath = Join-Path $backupFolder ($Name + '-before-' + [guid]::NewGuid().ToString('N') + '.lnk')
    Copy-Item -LiteralPath $shortcutPath -Destination $backupPath
    Write-Output "Previous shortcut backed up: $backupPath"
}
$shortcut.TargetPath = $pythonWindowless
$shortcut.Arguments = $launcherArguments
$shortcut.WorkingDirectory = $workspace
$shortcut.WindowStyle = 1
$shortcut.Description = 'ROE Thai offline. Map preload runs in the background for about one minute.'
$client = Join-Path (Split-Path -Parent $workspace) '32838/Europa_Client.exe'
if (Test-Path -LiteralPath $client -PathType Leaf) {
    $shortcut.IconLocation = $client + ',0'
}
$shortcut.Save()
$readback = $shortcutShell.CreateShortcut($shortcutPath)
if (![StringComparer]::OrdinalIgnoreCase.Equals($readback.TargetPath, $pythonWindowless) -or
        $readback.Arguments -ne $launcherArguments -or
        ![StringComparer]::OrdinalIgnoreCase.Equals($readback.WorkingDirectory, $workspace) -or
        $readback.WindowStyle -ne 1) {
    throw 'Shortcut readback differs from the requested Thai launcher.'
}
Write-Output "Thai parachute/menu shortcut: $shortcutPath"
