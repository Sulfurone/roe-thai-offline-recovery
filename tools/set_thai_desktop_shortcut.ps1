param([string]$Name = 'ROE')

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Name) -or $Name.Length -gt 64 -or $Name -match '[\\/:*?"<>|]') {
    throw 'Choose a single desktop shortcut name without path characters.'
}
$workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$launcher = Join-Path $workspace 'start_ingame_control.cmd'
$oldLauncher = Join-Path $workspace 'start_native_lobby.cmd'
$commandProcessor = Join-Path ([Environment]::SystemDirectory) 'cmd.exe'
$launcherArguments = '/d /s /c ""' + $launcher + '""'
if (!(Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'The Thai daytime/parachute launcher is missing.'
}
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutPath = Join-Path $desktop ($Name + '.lnk')
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
if (Test-Path -LiteralPath $shortcutPath) {
    $legacyTarget = @($launcher, $oldLauncher) | Where-Object {
        [StringComparer]::OrdinalIgnoreCase.Equals($_, $shortcut.TargetPath)
    }
    $knownCommand = [StringComparer]::OrdinalIgnoreCase.Equals($commandProcessor, $shortcut.TargetPath) -and
        [StringComparer]::OrdinalIgnoreCase.Equals($launcherArguments, $shortcut.Arguments)
    if (!$knownCommand -and (!$legacyTarget -or $shortcut.Arguments)) {
        throw 'Existing shortcut points elsewhere. Choose another name; unrelated or Steam shortcuts are preserved.'
    }
    if ($knownCommand -and $shortcut.WindowStyle -eq 1 -and
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
$shortcut.TargetPath = $commandProcessor
$shortcut.Arguments = $launcherArguments
$shortcut.WorkingDirectory = $workspace
$shortcut.WindowStyle = 1
$shortcut.Description = 'ROE Thai offline. Map preload takes about one minute.'
$client = Join-Path (Split-Path -Parent $workspace) '32838/Europa_Client.exe'
if (Test-Path -LiteralPath $client -PathType Leaf) {
    $shortcut.IconLocation = $client + ',0'
}
$shortcut.Save()
$readback = $shortcutShell.CreateShortcut($shortcutPath)
if (![StringComparer]::OrdinalIgnoreCase.Equals($readback.TargetPath, $commandProcessor) -or
        $readback.Arguments -ne $launcherArguments -or
        ![StringComparer]::OrdinalIgnoreCase.Equals($readback.WorkingDirectory, $workspace) -or
        $readback.WindowStyle -ne 1) {
    throw 'Shortcut readback differs from the requested Thai launcher.'
}
Write-Output "Thai parachute/menu shortcut: $shortcutPath"
