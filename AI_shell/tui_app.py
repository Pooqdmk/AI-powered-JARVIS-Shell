# ai_shell/tui_app.py

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Log, Button
from textual.containers import Horizontal
from textual.worker import Worker, get_current_worker
from .shell_core import execute_command
from .nlp_processor import get_smart_command
from .voice_interface import VoiceInterface

class AIShellApp(App):
    """A Textual app for the AI Shell."""

    TITLE = "AI Shell"
    SUB_TITLE = "Your Conversational Terminal"
    
    # CSS to fit 3 elements in one row
    CSS = """
    Horizontal {
        height: auto;
        dock: bottom;
        margin-bottom: 1;
    }
    Input {
        width: 70%;
    }
    #mic_btn {
        width: 15%;
        margin-left: 1;
    }
    #send_btn {
        width: 15%;
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("f2", "toggle_mic", "Toggle Mic"),
        ("ctrl+q", "quit", "Quit")
    ]

    def __init__(self):
        super().__init__()
        self.voice_engine = VoiceInterface()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output_log")
        # Layout: Input | Mic | Send
        with Horizontal():
            yield Input(placeholder="Ask me anything...", id="user_input")
            yield Button("🎤 Mic (F2)", id="mic_btn", variant="primary")
            yield Button("➤ Send", id="send_btn", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        output_log = self.query_one("#output_log", Log)
        output_log.write_line("Hello! I'm your AI Shell. 🤖")
        output_log.write_line("Type a command, use the Mic, or press Send.")
        output_log.write_line("To quit, type 'exit' or press Ctrl+Q.")
        self.query_one("#user_input", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "mic_btn":
            self.action_toggle_mic()
        elif event.button.id == "send_btn":
            # Call the shared submit function
            await self.submit_message()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Called when user presses Enter."""
        await self.submit_message()

    async def submit_message(self) -> None:
        """Shared function to process the input (from Enter key or Send button)."""
        input_box = self.query_one("#user_input", Input)
        user_input = input_box.value
        output_log = self.query_one("#output_log", Log)

        # Ignore empty input
        if not user_input.strip():
            return

        # Exit logic
        clean_input = user_input.strip().lower().rstrip(".,!?")
        if clean_input in ["exit", "quit"]:
            output_log.write_line("Exiting application...")
            self.exit()
            return

        # Clear input and show request
        input_box.clear()
        output_log.write_line(f"\n> Your request: '{user_input}'")
        
        # 1. Get Command
        command_to_run = get_smart_command(user_input)
        
        if "using LLM" not in command_to_run and "Used Layer" not in command_to_run:
             output_log.write_line(f"🤖 My interpretation: Executing '{command_to_run}'")
        
        # 2. Execute
        result = execute_command(command_to_run)
        output_log.write_line(result)
        
        # 3. Speak (in background thread)
        if len(result) < 200: 
            self.run_worker(lambda: self.voice_engine.speak(result), thread=True)
        else:
            self.run_worker(lambda: self.voice_engine.speak("Command executed. Output is displayed above."), thread=True)

        # Refocus input after sending (helpful for keyboard users)
        input_box.focus()

    def action_toggle_mic(self) -> None:
        """Action to run the voice listener."""
        input_box = self.query_one("#user_input", Input)
        input_box.placeholder = "🎤 Listening... Speak now!"
        input_box.disabled = True 
        self.run_worker(self.listen_worker, exclusive=True, thread=True)

    def listen_worker(self) -> None:
        text = self.voice_engine.listen()
        self.call_from_thread(self.on_listen_finished, text)

    def on_listen_finished(self, text: str) -> None:
        input_box = self.query_one("#user_input", Input)
        input_box.disabled = False
        input_box.placeholder = "Ask me anything..."
        
        if text:
            input_box.value = text
            input_box.focus()
        else:
            self.query_one("#output_log", Log).write_line("❌ Could not hear anything. Try again.")
            input_box.focus()