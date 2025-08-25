# ai_shell/tui_app.py

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Log
from .shell_core import execute_command
from .nlp_processor import get_smart_command

class AIShellApp(App):
    """A Textual app for the AI Shell."""

    TITLE = "AI Shell"
    SUB_TITLE = "Your Conversational Terminal"

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Log(id="output_log")
        yield Input(placeholder="Ask me anything or type a command...")
        yield Footer()

    def on_mount(self) -> None:
        """Called once when the app is first mounted."""
        # --- ADD WELCOME MESSAGE ---
        output_log = self.query_one("#output_log", Log)
        output_log.write_line("Hello! I'm your AI Shell. 🤖")
        output_log.write_line("You can type a command or ask me a question in plain English.")
        output_log.write_line("To quit the application, just type 'exit' and press Enter.")
        # ---------------------------
        
        # Set the initial focus on the input box
        self.query_one(Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Called when the user presses Enter in the Input widget."""
        user_input = event.value
        output_log = self.query_one("#output_log", Log)
        
        # Check for a custom "exit" command
        if user_input.strip().lower() == "exit":
            output_log.write_line("Exiting application...")
            self.exit() # Gracefully closes the Textual app
            return

        self.query_one(Input).clear()
        
        output_log.write_line(f"\n> Your request: '{user_input}'")
        command_to_run = get_smart_command(user_input)
        
        output_log.write_line(f"🤖 My interpretation: Executing '{command_to_run}'")
        
        result = execute_command(command_to_run)
        output_log.write_line(result)