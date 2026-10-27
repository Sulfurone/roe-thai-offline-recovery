$ErrorActionPreference = 'Stop'
$folder = 'F:\roe\recovery\private\runtime-diag-1'
$result = @{ process_bits = [IntPtr]::Size * 8; ok = $false }
try {
    if ([IntPtr]::Size -ne 4) { throw 'Run this validator using SysWOW64 PowerShell' }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class RoeForwarderTest {
    [StructLayout(LayoutKind.Sequential)]
    public struct MBI {
        public IntPtr BaseAddress, AllocationBase;
        public uint AllocationProtect;
        public UIntPtr RegionSize;
        public uint State, Protect, Type;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr LoadLibrary(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr GetModuleHandle(string name);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi, ExactSpelling=true, SetLastError=true)]
    public static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("kernel32.dll")]
    public static extern UIntPtr VirtualQuery(IntPtr address, out MBI info, UIntPtr size);
}
'@
    [RoeForwarderTest]::SetDllDirectory($folder) | Out-Null
    $proxy = [RoeForwarderTest]::LoadLibrary("$folder\DataEngine.diagnostic.dll")
    if ($proxy -eq [IntPtr]::Zero) { throw "LoadLibrary failed $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }
    $verified = @()
    foreach ($name in @('_BeginCollectPerfDatas@4','_EndCollectPerfDatas@0')) {
        $address = [RoeForwarderTest]::GetProcAddress($proxy, $name)
        if ($address -eq [IntPtr]::Zero) { throw "GetProcAddress failed for $name" }
        $original = [RoeForwarderTest]::GetModuleHandle('_ROE_Original_DataEngine.dll')
        if ($original -eq [IntPtr]::Zero) { throw 'Forwarding target was not loaded' }
        $info = New-Object RoeForwarderTest+MBI
        $size = [Runtime.InteropServices.Marshal]::SizeOf($info)
        [RoeForwarderTest]::VirtualQuery($address,[ref]$info,[UIntPtr]::new([uint32]$size)) | Out-Null
        if ($info.AllocationBase -ne $original) { throw "Forwarded pointer for $name does not belong to original DLL" }
        $verified += $name
    }
    $result.ok = $true
    $result.verified_exports = $verified
    $result.game_state_functions_called = 0
} catch {
    $result.error = $_.Exception.Message
}
$result | ConvertTo-Json | Set-Content -LiteralPath "$folder\forwarder-validation.json" -Encoding UTF8
if (-not $result.ok) { exit 1 }
