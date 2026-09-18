<#
.SYNOPSIS
    Queries hardware specifications and network details for a fleet node over SSH.
.EXAMPLE
    .\scripts\Audit-FleetNode.ps1 -NodeName nuc02
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$NodeName
)

Write-Host "=== Auditing Fleet Node: $NodeName ===" -ForegroundColor Cyan

# Gather remote specs in one remote command
$cmd = @'
echo "--- CPU ---"
lscpu | grep -E "Model name|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|CPU max MHz"
echo "--- RAM ---"
free -h | grep "Mem:"
sudo dmidecode -t memory | grep -E "Size:|Speed:|Locator:" | grep -v "No Module"
echo "--- STORAGE ---"
lsblk -o NAME,SIZE,TYPE,MODEL | grep -E "disk"
echo "--- NETWORK ---"
ip -br a
echo "--- TAILSCALE ---"
tailscale status 2>/dev/null | grep "$HOSTNAME" || echo "Tailscale: Not active"
echo "--- OS ---"
uname -srm
cat /etc/os-release | grep "PRETTY_NAME"
'@

ssh -o BatchMode=yes $NodeName "bash -c '$cmd'"
