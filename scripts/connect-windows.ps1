param([Parameter(Mandatory=$true)][string]$Server,[Parameter(Mandatory=$true)][string]$Account,[int]$LocalPort=8765,[int]$RemotePort=8765)
# Start the API and worker on Linux first. Host-key checking remains enabled.
Write-Host "After the SSH tunnel opens, visit http://127.0.0.1:$LocalPort"
ssh -N -o ExitOnForwardFailure=yes -L "${LocalPort}:127.0.0.1:${RemotePort}" "${Account}@${Server}"
