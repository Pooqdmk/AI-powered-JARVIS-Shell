# ai_shell/tui_app.py

import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Log, Button
from textual.containers import Horizontal, Container
from textual.worker import Worker, get_current_worker
from textual import events
from .shell_core import execute_command
from .nlp_processor import get_smart_command
from .voice_interface import VoiceInterface
from .autocomplete_engine import suggest
from .suggestion_widget import SuggestionList

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
    #suggestion_container {
        width: 70%;
        height: auto;
        dock: bottom;
        margin-bottom: 5;
        display: none;
        layer: suggestions;
    }
    #suggestion_list {
        width: 100%;
        height: auto;
        max-height: 10;
        border: solid $primary;
        background: $surface;
        min-height: 3;
    }
    """

    BINDINGS = [
        ("f2", "toggle_mic", "Toggle Mic"),
        ("ctrl+q", "quit", "Quit")
    ]

    def __init__(self):
        super().__init__()
        self.voice_engine = VoiceInterface()
        self._autocomplete_task: asyncio.Task | None = None
        self._autocomplete_debounce: asyncio.Task | None = None
        self._navigating_suggestions = False
        self._updating_from_suggestion = False  # Flag to prevent autocomplete when setting value from suggestion

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output_log")
        # Layout: Input | Mic | Send
        with Horizontal():
            yield Input(placeholder="Ask me anything...", id="user_input")
            yield Button("🎤 Mic (F2)", id="mic_btn", variant="primary")
            yield Button("➤ Send", id="send_btn", variant="success")
        # Suggestion dropdown container (positioned above input)
        yield Container(
            SuggestionList(id="suggestion_list"),
            id="suggestion_container"
        )
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
        # Hide suggestions when submitting
        self.hide_suggestions()
        await self.submit_message()
    
    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes to trigger autocomplete."""
        try:
            # Skip autocomplete if we're updating from a suggestion selection
            if self._updating_from_suggestion:
                self._updating_from_suggestion = False
                return
            
            # Cancel any pending debounce task
            if self._autocomplete_debounce and not self._autocomplete_debounce.done():
                try:
                    self._autocomplete_debounce.cancel()
                except Exception:
                    pass
            
            # Reset navigation flag when user types (not navigating anymore)
            self._navigating_suggestions = False
            
            input_value = event.value
            
            # Hide suggestions if input is empty
            if not input_value.strip():
                self.hide_suggestions()
                return
            
            # Debounce autocomplete calls (wait 100ms after user stops typing for faster response)
            async def debounced_autocomplete():
                try:
                    await asyncio.sleep(0.1)  # Reduced from 300ms to 100ms for faster response
                    # Check if input still has content (user might have cleared it)
                    current_input = self.query_one("#user_input", Input).value
                    if current_input.strip() and current_input == input_value:
                        await self.update_autocomplete_suggestions(input_value)
                except asyncio.CancelledError:
                    pass  # Expected when user continues typing
                except Exception:
                    # Silently handle errors
                    pass
            
            self._autocomplete_debounce = asyncio.create_task(debounced_autocomplete())
        except Exception:
            # Silently handle errors
            pass
    
    async def update_autocomplete_suggestions(self, text: str) -> None:
        """Update autocomplete suggestions based on current input."""
        try:
            # Call the BART autocomplete engine
            suggestions = await suggest(text, limit=6)
            
            suggestion_list = self.query_one("#suggestion_list", SuggestionList)
            suggestion_container = self.query_one("#suggestion_container", Container)
            
            if suggestions:
                suggestion_list.update_suggestions(suggestions)
                suggestion_container.display = True
                # Force a refresh to ensure the container is visible
                suggestion_container.refresh()
            else:
                self.hide_suggestions()
        except Exception:
            # Silently handle errors
            self.hide_suggestions()
    
    def hide_suggestions(self) -> None:
        """Hide the suggestion dropdown."""
        try:
            suggestion_container = self.query_one("#suggestion_container", Container)
            suggestion_list = self.query_one("#suggestion_list", SuggestionList)
            suggestion_container.display = False
            suggestion_list.hide()
            suggestion_container.refresh()
        except Exception:
            # Widgets might not be mounted yet
            pass
    
    def on_suggestion_list_selected(self, event: SuggestionList.Selected) -> None:
        """Handle selection of a suggestion - updates the input with selected text."""
        try:
            input_box = self.query_one("#user_input", Input)
            # Set flag to prevent autocomplete from triggering when we update the value
            self._updating_from_suggestion = True
            # Update the input with the selected suggestion
            input_box.value = event.suggestion
            self.hide_suggestions()
            input_box.focus()
            self._navigating_suggestions = False
        except Exception:
            # Silently handle any errors
            pass
    
    async def on_key(self, event: events.Key) -> None:
        """Handle keyboard navigation for suggestions."""
        try:
            input_box = self.query_one("#user_input", Input)
            suggestion_list = self.query_one("#suggestion_list", SuggestionList)
            suggestion_container = self.query_one("#suggestion_container", Container)
            
            # Check if suggestions are visible
            if suggestion_container.display and suggestion_list._visible:
                option_count = len(suggestion_list._suggestions)
                
                if event.key == "down":
                    # If suggestion list already has focus, let it handle navigation
                    if suggestion_list.has_focus:
                        # Let OptionList handle the down arrow
                        return
                    # Otherwise, move focus to suggestion list and highlight first item
                    self._navigating_suggestions = True
                    suggestion_list.focus()
                    if option_count > 0:
                        suggestion_list.highlighted = 0
                    event.prevent_default()
                    return
                elif event.key == "up":
                    # If already in suggestions, let it handle it
                    if suggestion_list.has_focus:
                        # Let OptionList handle the up arrow
                        return
                    # Otherwise, move to suggestions
                    self._navigating_suggestions = True
                    suggestion_list.focus()
                    if option_count > 0:
                        suggestion_list.highlighted = option_count - 1
                    event.prevent_default()
                    return
                elif event.key == "escape":
                    # Hide suggestions and return focus to input
                    self.hide_suggestions()
                    input_box.focus()
                    self._navigating_suggestions = False
                    event.prevent_default()
                    return
        except Exception:
            # Silently handle any errors
            pass

    async def submit_message(self) -> None:
        """Shared function to process the input (from Enter key or Send button)."""
        # Hide suggestions when submitting
        self.hide_suggestions()
        self._navigating_suggestions = False
        
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
            # Trigger autocomplete for the voice input
            self.post_message(Input.Changed(input_box, text))
        else:
            self.query_one("#output_log", Log).write_line("❌ Could not hear anything. Try again.")
            input_box.focus()