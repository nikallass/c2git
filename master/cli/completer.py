from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.completion import CompleteEvent
from .menu import Menu

class CommandCompleter(Completer):
    def __init__(self, menu: Menu):
        self.menu = menu
        self.interactive_commands = ['back', 'jobs']

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        word = document.get_word_before_cursor()
        text_before = document.text_before_cursor
        first_word = text_before.strip().split()[0] if text_before.strip() else ""
        
        # Check if we're in interactive mode
        is_interactive = '>' in text_before
        
        if is_interactive:
            # In interactive mode, suggest interactive commands
            for cmd in self.interactive_commands:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
        else:
            # For interact and run commands, suggest session IDs
            if first_word in ["interact", "run"]:
                sessions = [s.id for s in self.menu.session_manager.sessions.values()]
                for session_id in sessions:
                    if session_id.startswith(word):
                        yield Completion(session_id, start_position=-len(word))
            else:
                # Get all available commands
                commands = self.menu.get_commands()
                
                # Return matching commands
                for cmd in commands:
                    if cmd.startswith(word):
                        yield Completion(cmd, start_position=-len(word))
