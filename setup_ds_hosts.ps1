# Double-click or:  powershell -ExecutionPolicy Bypass -File .\setup_ds_hosts.ps1
# If not elevated, this relaunches itself via UAC.
$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$ip = "10.162.6.161"
$name = "ds.local.ai"
$line = "$ip`t$name"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $script = $MyInvocation.MyCommand.Path
    Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$script`""
    )
    exit $LASTEXITCODE
}

$existing = Get-Content -Path $hostsPath
if ($existing | Where-Object { $_ -match '^\s*[\d\.:a-fA-F]+\s+ds\.local\.ai(\s|$)' }) {
    $updated = $existing | ForEach-Object {
        if ($_ -match '^\s*[\d\.:a-fA-F]+\s+ds\.local\.ai(\s|$)') { $line } else { $_ }
    }
    Set-Content -Path $hostsPath -Value $updated -Encoding ascii
    Write-Host "Updated existing hosts entry: $line"
} else {
    Add-Content -Path $hostsPath -Value "`r`n$line" -Encoding ascii
    Write-Host "Added hosts entry: $line"
}

ipconfig /flushdns | Out-Null
Write-Host "Flushed DNS cache."
Write-Host "Verify with:  ping ds.local.ai"
Write-Host "nslookup ignores hosts because DNS is 127.0.0.1; ping/Python use hosts."
Write-Host "Press Enter to close."
[void][Console]::ReadLine()
