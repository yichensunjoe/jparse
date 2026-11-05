# Run on Windows. Exercise the real launcher extraction under an ACL that
# permits creating/writing files but denies deleting or moving directories.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = Join-Path $env:RUNNER_TEMP ('jparse-acl-test-' + [guid]::NewGuid().ToString('N'))
$parent = Join-Path $root 'runtime'
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$originalAcl = Get-Acl -LiteralPath $parent
try {
    $stub = Join-Path $root 'launcher-test.exe'
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    & $compiler /nologo /target:winexe /platform:x64 "/out:$stub" `
        /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.IO.Compression.dll `
        /r:System.IO.Compression.FileSystem.dll (Join-Path $PWD 'scripts\windows_launcher.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Could not compile launcher' }
    $assembly = [Reflection.Assembly]::LoadFrom($stub)
    $type = $assembly.GetType('JParseLauncher', $true)
    $method = $type.GetMethod('ExtractRuntime', [Reflection.BindingFlags]'NonPublic,Static')
    if (!$method) { throw 'ExtractRuntime not found' }

    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Get-Acl -LiteralPath $parent
    $denyChild = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid, [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles,
        [Security.AccessControl.InheritanceFlags]::None,
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Deny)
    $denyDirectory = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid, [Security.AccessControl.FileSystemRights]::Delete,
        [Security.AccessControl.InheritanceFlags]::ContainerInherit,
        [Security.AccessControl.PropagationFlags]::InheritOnly,
        [Security.AccessControl.AccessControlType]::Deny)
    $acl.AddAccessRule($denyChild)
    $acl.AddAccessRule($denyDirectory)
    Set-Acl -LiteralPath $parent -AclObject $acl

    function New-TestPayload([string]$name, [bool]$invalid) {
        $zipPath = Join-Path $root ($name + '.zip')
        $zip = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
        try {
            $names = @(
                'python/python.exe', 'python/pythonw.exe', 'ocr-python/python.exe',
                'ocr-models/official_models/placeholder', 'project/src/desktop_app_windows.py',
                'jre/bin/java.exe', 'models/layout.onnx', 'models/SourceHanSerifCN-Regular.ttf',
                'models/SourceHanSerifCN-Bold.ttf', 'models/SourceHanSansCN-Regular.ttf',
                'models/SourceHanSansCN-Bold.ttf'
            )
            if ($invalid) { $names += '../escape.txt' }
            foreach ($entryName in $names) {
                $entry = $zip.CreateEntry($entryName)
                $writer = [IO.StreamWriter]::new($entry.Open())
                try { $writer.Write('test') } finally { $writer.Dispose() }
            }
        } finally { $zip.Dispose() }
        $bytes = [IO.File]::ReadAllBytes($zipPath)
        $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
        $container = Join-Path $root ($name + '.bin')
        $output = [IO.File]::Create($container)
        try {
            $output.Write($bytes, 0, $bytes.Length)
            $output.Write([byte[]]::new(56), 0, 56)
        } finally { $output.Dispose() }
        return @{ Path = $container; Size = [long]$bytes.Length; Hash = $hash }
    }

    function Invoke-Extraction($payload, [string]$destination) {
        $stream = [IO.File]::OpenRead($payload.Path)
        $arguments = [object[]]::new(5)
        $arguments[0] = $stream
        $arguments[1] = $payload.Size
        $arguments[2] = $payload.Hash
        $arguments[3] = [string]$parent
        $arguments[4] = [string]$destination
        try {
            $method.Invoke($null, $arguments) | Out-Null
        } catch [Reflection.TargetInvocationException] {
            throw $_.Exception.InnerException
        } finally { $stream.Dispose() }
    }

    $payload = New-TestPayload 'valid' $false
    $destination = Join-Path $parent 'runtime-candidate'
    Invoke-Extraction $payload $destination
    $expected = [BitConverter]::ToString($payload.Hash).Replace('-', '').ToLowerInvariant()
    $actual = [IO.File]::ReadAllText((Join-Path $destination '.complete')).Trim()
    if ($actual -ne $expected) { throw 'Completion marker does not identify the exact payload' }
    Write-Host 'Extraction succeeded without directory delete permission'

    $invalid = New-TestPayload 'invalid' $true
    $badDestination = Join-Path $parent 'invalid-candidate'
    $actualError = $null
    try { Invoke-Extraction $invalid $badDestination }
    catch { $actualError = $_.Exception }
    if ($actualError -isnot [IO.InvalidDataException]) {
        throw "Original invalid-archive error was masked by cleanup: $actualError"
    }
    Write-Host 'Original extraction error was preserved when cleanup failed'
} finally {
    if (Test-Path $parent) {
        try { Set-Acl -LiteralPath $parent -AclObject $originalAcl } catch { }
    }
    try { Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction Stop } catch { }
}
