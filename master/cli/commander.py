import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from master.core import SessionManager, JobManager
from .menu import Menu
from .completer import CommandCompleter

class Commander:
    def __init__(self, session_manager: SessionManager, job_manager: JobManager):
        self.session_manager = session_manager
        self.job_manager = job_manager
        self.menu = Menu(session_manager, job_manager)
        self.completer = CommandCompleter(self.menu)
        self.session = PromptSession(completer=self.completer)
        self._running = False

    async def start(self):
        """Start the interactive console"""
        self._running = True
        print("C2Git Command & Control")
        print("Type 'help' for available commands")

        with patch_stdout():
            while self._running:
                try:
                    command = await self.session.prompt_async("c2git> ")
                    if command.strip():
                        await self.menu.handle_command(command)
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break

    async def stop(self):
        """Stop the interactive console"""
        if not self._running:
            return
        self._running = False
        # Cancel any pending prompt
        if hasattr(self.session, '_default_buffer'):
            self.session._default_buffer.reset()
        # Cancel any pending tasks
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
