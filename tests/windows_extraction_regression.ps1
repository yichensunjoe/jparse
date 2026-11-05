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

    $probe = Join-Path $parent 'delete-denial-probe'
    New-Item -ItemType Directory -Path $probe | Out-Null
    $moveDenied = $false
    try { [IO.Directory]::Move($probe, $probe + '-moved') }
    catch { $moveDenied = $true }
    if (!$moveDenied) { throw 'Test ACL did not deny directory renaming' }

    # Windows file-share locks are enforced across processes and sessions.
    $lockMethod = $type.GetMethod('AcquireRuntimeLock', [Reflection.BindingFlags]'NonPublic,Static')
    if (!$lockMethod) { throw 'AcquireRuntimeLock not found' }
    $lockKey = 'a' * 64
    $lockArgs = [object[]]::new(2)
    $lockArgs[0] = [string]$parent
    $lockArgs[1] = [string]$lockKey
    $held = $lockMethod.Invoke($null, $lockArgs)
    $worker = Join-Path $root 'lock-worker.ps1'
    @'
param([string]$LockPath, [string]$Expected, [string]$Stub, [string]$Signal, [string]$Parent, [string]$Key)
if ($Expected -eq 'wait') {
    try {
        $assembly = [Reflection.Assembly]::LoadFrom($Stub)
        $type = $assembly.GetType('JParseLauncher', $true)
        $method = $type.GetMethod('AcquireRuntimeLock', [Reflection.BindingFlags]'NonPublic,Static')
        $arguments = [object[]]::new(2)
        $arguments[0] = [string]$Parent
        $arguments[1] = [string]$Key
        [IO.File]::WriteAllText($Signal + '.ready', 'ready')
        $acquired = $method.Invoke($null, $arguments)
        try { [IO.File]::WriteAllText($Signal, 'acquired') } finally { $acquired.Dispose() }
        exit 0
    } catch { exit 1 }
}
try {
    $file = [IO.FileStream]::new($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $file.Dispose()
    if ($Expected -eq 'locked') { exit 1 } else { exit 0 }
} catch {
    $errorObject = $_.Exception
    while ($errorObject.InnerException) { $errorObject = $errorObject.InnerException }
    if ($Expected -eq 'locked' -and $errorObject -is [IO.IOException]) { exit 0 } else { exit 1 }
}
'@ | Set-Content -LiteralPath $worker -Encoding utf8
    $pwsh = (Get-Process -Id $PID).Path
    $lockPath = Join-Path $parent ('.lock-' + $lockKey)
    $waiting = $null
    try {
        & $pwsh -NoProfile -NonInteractive -File $worker $lockPath 'locked'
        if ($LASTEXITCODE -ne 0) { throw 'A second process obtained a held runtime lock' }
        $signal = Join-Path $root 'lock-acquired.txt'
        $waiting = Start-Process -FilePath $pwsh -PassThru -ArgumentList @(
            '-NoProfile', '-NonInteractive', '-File', ('"' + $worker + '"'),
            ('"' + $lockPath + '"'), 'wait', ('"' + $stub + '"'),
            ('"' + $signal + '"'), ('"' + $parent + '"'), $lockKey
        )
        $readyDeadline = (Get-Date).AddSeconds(10)
        while (!(Test-Path ($signal + '.ready')) -and (Get-Date) -lt $readyDeadline) {
            Start-Sleep -Milliseconds 100
        }
        if (!(Test-Path ($signal + '.ready'))) { throw 'Waiting process did not start' }
        Start-Sleep -Milliseconds 500
        if (Test-Path $signal) { throw 'Waiting process acquired a held runtime lock' }
    } finally { $held.Dispose() }
    if (!$waiting.WaitForExit(15000) -or $waiting.ExitCode -ne 0 -or !(Test-Path $signal)) {
        throw 'Waiting process did not acquire the runtime lock after release'
    }
    & $pwsh -NoProfile -NonInteractive -File $worker $lockPath 'free'
    if ($LASTEXITCODE -ne 0) { throw 'Runtime lock was not released' }
    Write-Host 'Runtime file lock excludes other processes and releases correctly'

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
        } catch {
            $underlying = $_.Exception
            while ($underlying.InnerException) { $underlying = $underlying.InnerException }
            throw $underlying
        } finally { $stream.Dispose() }
    }

    $payload = New-TestPayload 'valid' $false
    $expected = [BitConverter]::ToString($payload.Hash).Replace('-', '').ToLowerInvariant()
    $destination = Join-Path $parent ($expected.Substring(0, 12) + '-1234abcd')
    Invoke-Extraction $payload $destination
    $actual = [IO.File]::ReadAllText((Join-Path $destination '.complete')).Trim()
    if ($actual -ne $expected) { throw 'Completion marker does not identify the exact payload' }
    Write-Host 'Extraction succeeded without directory delete permission'

    $incomplete = Join-Path $parent ($expected.Substring(0, 12) + '-incomplete')
    New-Item -ItemType Directory -Path $incomplete | Out-Null
    $findReady = $type.GetMethod('FindReadyRuntime', [Reflection.BindingFlags]'NonPublic,Static')
    if (!$findReady) { throw 'FindReadyRuntime not found' }
    $findArgs = [object[]]::new(2)
    $findArgs[0] = [string]$parent
    $findArgs[1] = [string]$expected
    if ([string]$findReady.Invoke($null, $findArgs) -ne $destination) {
        throw 'A completed runtime was not reused or an incomplete one was selected'
    }
    Write-Host 'Completed runtime was reused and incomplete extraction was ignored'

    $resumePayload = New-TestPayload 'resume' $false
    $resumeKey = [BitConverter]::ToString($resumePayload.Hash).Replace('-', '').ToLowerInvariant()
    $resumeDestination = Join-Path $parent ($resumeKey.Substring(0, 12) + '-resume01')
    New-Item -ItemType Directory -Path (Join-Path $resumeDestination 'python') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $resumeDestination '.payload'), $resumeKey)
    [IO.File]::WriteAllText((Join-Path $resumeDestination 'python/python.exe'), 'truncated')
    $findIncomplete = $type.GetMethod('FindIncompleteRuntime', [Reflection.BindingFlags]'NonPublic,Static')
    if (!$findIncomplete) { throw 'FindIncompleteRuntime not found' }
    $resumeArgs = [object[]]::new(2)
    $resumeArgs[0] = [string]$parent
    $resumeArgs[1] = [string]$resumeKey
    if ([string]$findIncomplete.Invoke($null, $resumeArgs) -ne $resumeDestination) {
        throw 'Interrupted runtime was not selected for safe reuse'
    }
    Invoke-Extraction $resumePayload $resumeDestination
    if ([IO.File]::ReadAllText((Join-Path $resumeDestination 'python/python.exe')) -ne 'test') {
        throw 'Interrupted file was not safely replaced'
    }
    Write-Host 'Interrupted extraction resumed without leaving another runtime directory'

    $invalid = New-TestPayload 'invalid' $true
    $badDestination = Join-Path $parent 'invalid-candidate'
    $actualError = $null
    try { Invoke-Extraction $invalid $badDestination }
    catch {
        $actualError = $_.Exception
        while ($actualError.InnerException) { $actualError = $actualError.InnerException }
    }
    if ($actualError -isnot [IO.InvalidDataException]) {
        throw "Original invalid-archive error was masked by cleanup: $actualError"
    }
    Write-Host 'Original extraction error was preserved'
} finally {
    if (Test-Path $parent) {
        try { Set-Acl -LiteralPath $parent -AclObject $originalAcl } catch { }
    }
    try { Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction Stop } catch { }
}
