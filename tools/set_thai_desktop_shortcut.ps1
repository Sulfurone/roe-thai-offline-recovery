param([string]$Name = 'ROE')

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Name) -or $Name.Length -gt 64 -or $Name -match '[\\/:*?"<>|]') {
    throw 'Choose a single desktop shortcut name without path characters.'
}
$workspace = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$launcher = Join-Path $workspace 'start_ingame_control.cmd'
$oldLauncher = Join-Path $workspace 'start_native_lobby.cmd'
if (!(Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'The Thai daytime/parachute launcher is missing.'
}
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutPath = Join-Path $desktop ($Name + '.lnk')
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
if (Test-Path -LiteralPath $shortcutPath) {
    $knownTarget = @($launcher, $oldLauncher) | Where-Object {
        [StringComparer]::OrdinalIgnoreCase.Equals($_, $shortcut.TargetPath)
    }
    if (!$knownTarget -or $shortcut.Arguments) {
        throw 'Existing shortcut points elsewhere. Choose another name; unrelated or Steam shortcuts are preserved.'
    }
    if ([StringComparer]::OrdinalIgnoreCase.Equals($shortcut.TargetPath, $launcher) -and
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
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $workspace
$shortcut.Description = 'Thai offline: daytime parachute and F6 control menu'
$client = Join-Path (Split-Path -Parent $workspace) '32838/Europa_Client.exe'
if (Test-Path -LiteralPath $client -PathType Leaf) {
    $shortcut.IconLocation = $client + ',0'
}
$shortcut.Save()
$readback = $shortcutShell.CreateShortcut($shortcutPath)
if (![StringComparer]::OrdinalIgnoreCase.Equals($readback.TargetPath, $launcher)) {
    throw 'Shortcut readback differs from the requested Thai launcher.'
}
Write-Output "Thai parachute/menu shortcut: $shortcutPath"
