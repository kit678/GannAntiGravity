
# Define the ports to kill
$ports = @(8001, 5173)

# Function to kill process by port
function Kill-PortProcess {
    param([int]$port)
    $connection = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connection) {
        $pid_val = $connection.OwningProcess
        Write-Host "Killing process ID $pid_val on port $port..."
        Stop-Process -Id $pid_val -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "No process found on port $port."
    }
}

# Kill processes on defined ports
foreach ($port in $ports) {
    Kill-PortProcess -port $port
}

# Wait a moment to ensure ports are freed
Start-Sleep -Seconds 2

# Start Backend Server (New Window)
Write-Host "Starting Backend Server..."
Start-Process -FilePath "python" -ArgumentList "main.py" -WorkingDirectory "c:\Dev\GannTesting\gann-visualizer\backend"

# Start Frontend Server (New Window)
Write-Host "Starting Frontend Server..."
Start-Process -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory "c:\Dev\GannTesting\gann-visualizer\frontend"

Write-Host "Servers restarted successfully! check the new windows for logs."
