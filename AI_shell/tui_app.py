# ai_shell/tui_app.py

import asyncio
import logging
from typing import List

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Log, Button, Static
from textual.containers import Horizontal, Container
from textual.reactive import reactive
from textual.binding import Binding
from textual.events import Resize

from .shell_core import execute_command
from .nlp_processor import get_smart_command
from .voice_interface import VoiceInterface
from .autocomplete_engine import suggest, clear_cache


# ============================================================
#                         LOGGING
# ============================================================
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )


# ============================================================
#                AUTOCOMPLETE POPUP WIDGET
# ============================================================
class SuggestionPopup(Static):
    """VS Code–style dropdown suggestion list."""

    suggestions: reactive[List[str]] = reactive([])
    selected_index: reactive[int] = reactive(0)
    visible: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    SuggestionPopup {
        background: $panel;
        border: round $primary;
        padding: 1;
        width: 80%;
    }
    SuggestionPopup > .item.--selected {
        background: $accent;
        color: $text;
    }
    """

    def watch_suggestions(self, old, new):
        self.selected_index = 0
        self.visible = bool(new)
        logger.info(f"[AC] Suggestions updated: {len(new)} items")

    def render(self):
        if not self.visible or not self.suggestions:
            return ""
        lines = []
        for i, s in enumerate(self.suggestions):
            mark = "→" if i == self.selected_index else " "
            lines.append(f"{mark} {s}")
        return "\n".join(lines)

    def move_up(self):
        if self.suggestions:
            self.selected_index = (self.selected_index - 1) % len(self.suggestions)
            logger.info(f"[AC] Moved up → {self.selected_index}")

    def move_down(self):
        if self.suggestions:
            self.selected_index = (self.selected_index + 1) % len(self.suggestions)
            logger.info(f"[AC] Moved down → {self.selected_index}")

    def get_selected(self) -> str:
        if not self.suggestions:
            return ""
        return self.suggestions[self.selected_index]


# ============================================================
#                      MAIN APP
# ============================================================
class AIShellApp(App):

    TITLE = "AI Shell"
    SUB_TITLE = "Your Conversational Terminal"

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
    SuggestionPopup {
        dock: bottom;
        margin-bottom: 1;
        width: 70%;
    }
    """

    BINDINGS = [
        Binding("tab", "accept_completion", "Accept completion"),
        Binding("enter", "submit_message", "Submit message"),
        Binding("escape", "close_suggestions", "Close suggestions"),
        Binding("up", "navigate_up", "Up"),
        Binding("down", "navigate_down", "Down"),
        Binding("f2", "toggle_mic", "Toggle Mic"),
        Binding("f5", "clear_cache", "Clear Autocomplete Cache"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.voice_engine = VoiceInterface()
        self._debounce_task = None
        self._debounce_ms = 180
        self._last_text = ""

    # ============================================================
    #                 COMPOSE UI
    # ============================================================
    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output_log")

        with Container():
            yield SuggestionPopup(id="suggestions")

            with Horizontal():
                yield Input(placeholder="Ask me anything...", id="user_input")
                yield Button("🎤 Mic (F2)", id="mic_btn", variant="primary")
                yield Button("➤ Send", id="send_btn", variant="success")

        yield Footer()

    # ============================================================
    #                  MOUNT
    # ============================================================
    def on_mount(self):
        log = self.query_one("#output_log", Log)
        log.write_line("Hello! I'm your AI Shell. 🤖")
        log.write_line("Autocomplete ready. ↑↓ navigate, TAB accept.")
        logger.info("[INIT] UI mounted successfully.")
        self.query_one("#user_input", Input).focus()

    # ============================================================
    #               WINDOW RESIZE HANDLER
    # ============================================================
    def on_resize(self, event: Resize):
        logger.info(f"[UI] Terminal resized to {event.size.width}x{event.size.height}")

    # ============================================================
    #               BUTTON EVENTS
    # ============================================================
    async def on_button_pressed(self, event):
        if event.button.id == "mic_btn":
            logger.info("[MIC] Mic button pressed")
            self.action_toggle_mic()
        elif event.button.id == "send_btn":
            logger.info("[SEND] Send button pressed")
            await self.action_submit_message()

    # ============================================================
    #          INPUT SUBMIT (ENTER KEY)
    # ============================================================
    async def on_input_submitted(self, event):
        await self.action_submit_message()

    # ============================================================
    #            AUTOCOMPLETE DEBOUNCE HANDLER
    # ============================================================
    async def on_input_changed(self, event: Input.Changed):
        text = event.value

        if text == self._last_text:
            return

        logger.info(f"[AC] Input changed: '{text}'")
        self._last_text = text

        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        self._debounce_task = asyncio.create_task(self._debounced_suggest(text))

    async def _debounced_suggest(self, text: str):
        try:
            await asyncio.sleep(self._debounce_ms / 1000)
            suggestions = await suggest(text)
            popup = self.query_one("#suggestions", SuggestionPopup)
            popup.suggestions = suggestions
            popup.visible = bool(suggestions)

            logger.info(f"[AC] Suggestions returned: {len(suggestions)}")

        except asyncio.CancelledError:
            logger.info("[AC] Suggestion debounce cancelled")

    # ============================================================
    #               AUTOCOMPLETE ACTIONS
    # ============================================================
    async def action_accept_completion(self):
        popup = self.query_one("#suggestions", SuggestionPopup)
        input_box = self.query_one("#user_input", Input)

        if popup.visible and popup.suggestions:
            chosen = popup.get_selected()
            logger.info(f"[AC] Completion accepted: '{chosen}'")

            input_box.value = chosen
            popup.visible = False
            popup.suggestions = []
            self._last_text = chosen

    async def action_close_suggestions(self):
        popup = self.query_one("#suggestions", SuggestionPopup)
        popup.visible = False
        popup.suggestions = []
        logger.info("[AC] Suggestions closed")

    async def action_navigate_up(self):
        popup = self.query_one("#suggestions", SuggestionPopup)
        if popup.visible:
            popup.move_up()

    async def action_navigate_down(self):
        popup = self.query_one("#suggestions", SuggestionPopup)
        if popup.visible:
            popup.move_down()

    async def action_clear_cache(self):
        clear_cache()
        self.query_one("#output_log", Log).write_line("⚠️ Cache cleared.")
        logger.info("[AC] Autocomplete cache cleared")

    # ============================================================
    #                  SUBMIT MESSAGE LOGIC
    # ============================================================
    async def action_submit_message(self):
        input_box = self.query_one("#user_input", Input)
        popup = self.query_one("#suggestions", SuggestionPopup)
        log = self.query_one("#output_log", Log)

        # If suggestions open, first Enter accepts
        if popup.visible and popup.suggestions:
            chosen = popup.get_selected()
            input_box.value = chosen
            popup.visible = False
            popup.suggestions = []
            logger.info(f"[AC] Enter → accepted suggestion: {chosen}")
            return

        user_input = input_box.value.strip()
        if not user_input:
            return

        if user_input.lower() in ["exit", "quit"]:
            log.write_line("Exiting application...")
            logger.info("[SYS] App exit requested")
            self.exit()
            return

        # Clear UI + show input
        input_box.clear()
        log.write_line(f"\n> Your request: {user_input}")
        logger.info(f"[CMD] User request: {user_input}")

        # Convert NL → Command
        command = get_smart_command(user_input)
        logger.info(f"[CMD] Smart command: {command}")

        log.write_line(f"🤖 Executing: {command}")

        # Run system command
        result = execute_command(command)
        log.write_line(result)
        logger.info("[CMD] Command executed successfully")

        # Speak short results
        msg = result if len(result) < 200 else "Command executed."
        self.run_worker(lambda: self.voice_engine.speak(msg), thread=True)

        input_box.focus()

    # ============================================================
    #                      VOICE INPUT
    # ============================================================
    def action_toggle_mic(self):
        input_box = self.query_one("#user_input", Input)
        input_box.placeholder = "🎤 Listening..."
        input_box.disabled = True

        logger.info("[MIC] Listening started")
        self.run_worker(self._listen_worker, exclusive=True, thread=True)

    def _listen_worker(self):
        text = self.voice_engine.listen()
        self.call_from_thread(self._listen_finished, text)

    def _listen_finished(self, text: str):
        input_box = self.query_one("#user_input", Input)
        input_box.disabled = False
        input_box.placeholder = "Ask me anything..."

        if text:
            input_box.value = text
            logger.info(f"[MIC] Heard: {text}")
        else:
            self.query_one("#output_log", Log).write_line("❌ Could not hear anything.")
            logger.warning("[MIC] No speech detected")

        input_box.focus()


if __name__ == "__main__":
    AIShellApp().run()
