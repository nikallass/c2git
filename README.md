# C2Git - Command & Control over Git

C2Git is a covert command and control (C2) framework that uses Git repositories as a communication channel between the master and slave nodes. It provides a secure way to execute commands on remote systems while hiding the C2 traffic in legitimate-looking Git commits.

![demo](https://github.com/nikallass/c2git/blob/main/demo.gif)

## Quick Start

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/c2git.git
cd c2git
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a private GitHub repository and generate a Personal Access Token (PAT)

4. Copy example config and edit:
```bash
cp config/.env.example config/.env
# Edit config/.env with your GitHub details and encryption key
```

### Running Master

```bash
python c2git.py master
```

### Generating and Running Agents

Generate agent files:
```bash
# Generate Bash agent slave.sh in current dir
python c2git.py generate sh

# Generate PowerShell agent
python c2git.py generate ps1 -o slave.ps1

# Generate Python agent
python c2git.py generate py -o /custom/path/slave.py
```

Run an agent:
```bash
# Bash agent
./slave.sh

# PowerShell agent (not tested at all)
.\slave.ps1 -Verbose

# Python agent (a little bit tested)
python slave.py -v
```

## Technical Details

### Communication Protocol

C2Git uses a state-based protocol stored in a `state` file:

- **State 0**: Command sent, waiting for execution
- **State 1**: Response ready, waiting for master to read
- **State 2**: Ready for new command

### Branch Naming

Each slave gets a unique branch name using the first 10 characters of the MD5 hash of its hostname:
```python
branch_name = hashlib.md5(hostname.encode()).hexdigest()[:10]
```
### Encryption

All commands and responses are encrypted using AES-256-CBC with PBKDF2 key derivation:
- 100,000 iterations
- Random salt
- Base64 encoded output

#### Manual Encryption/Decryption

Encrypt a string:
```bash
python c2git.py encrypt "hello world"
```

Decrypt a string:
```bash
python c2git.py decrypt "U2FsdGVkX19..."
```

## Configuration Methods

### 1. Environment Variables

```bash
export C2GIT_REPO_USER="github_username"
export C2GIT_REPO_NAME="repo_name"
export C2GIT_GITHUB_TOKEN="github_pat_11..."
export C2GIT_ENCRYPTION_KEY="your_secret_key"
```

### 2. Config File (config/config.yaml)

```yaml
repo_user: "github_username"
repo_name: "repo_name"
github_token: "github_pat_11..."
encryption_key: "your_secret_key"
```

### 3. .env File (config/.env)

```
C2GIT_REPO_USER=github_username
C2GIT_REPO_NAME=repo_name
C2GIT_GITHUB_TOKEN=github_pat_11...
C2GIT_ENCRYPTION_KEY=your_secret_key
```

## Example Workflow

1. **Slave Initialization**:
```bash
./slave.sh -v
# 1. Creates local repo
# 2. Generates branch from hostname
# 3. Creates host file with encrypted hostname
# 4. Sets state=2 (ready)
```

2. **Master Reads New Session**:
```bash
python c2git.py master
# In C2Git console:
sessions
# Shows new session with hostname
```

3. **Send Command**:
```bash
# In C2Git console:
interact abc123def0
> whoami
# 1. Encrypts "whoami"
# 2. Writes to command.txt
# 3. Sets state=0
```

4. **Slave Executes**:
```bash
# Slave detects state=0
# 1. Decrypts command
# 2. Executes whoami
# 3. Encrypts output
# 4. Writes to response.txt
# 5. Sets state=1
```

5. **Master Reads Response**:
```bash
# Master detects state=1
# 1. Reads response.txt
# 2. Decrypts response
# 3. Displays output
# 4. Sets state=2
```

## Features

- Covert communication through Git repositories
- AES-256 encryption for commands and responses
- Support for multiple simultaneous sessions
- Cross-platform agents (Linux, macOS, Windows)
- Job queuing and management
- Interactive session mode
- Command completion
- Heartbeat monitoring
- Session persistence

## Security Considerations

1. **Git Repository**:
   - Use private repositories only
   - Implement IP restrictions
   - Regular token rotation

2. **Communication**:
   - All data encrypted with AES-256
   - Random check intervals
   - Added jitter to avoid detection
   - No plaintext sensitive data

3. **Operational Security**:
   - Clean commit history
   - Legitimate-looking commit messages
   - Regular cleanup of old sessions
   - Secure key management

## Dependencies

- Python 3.7+
- GitPython
- prompt_toolkit
- PyYAML
- cryptography
- prettytable

## Disclaimer

This tool is for educational purposes only. Users are responsible for complying with applicable laws and regulations.
