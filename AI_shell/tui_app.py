# Updated ai_shell/tui_app.py

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
from .rag_engine import ensure_vectorstore, rag_answer

def format_rag_dict(data: dict) -> str:
    lines = []
    

    if "answer" in data:
        lines.append(data["answer"])
        lines.append("")

    if data.get("references"):
        lines.append("📂 Sources:")
        for r in data["references"]:
            lines.append(f" • {r}")
        lines.append("")

    if data.get("suggestions"):
        lines.append("💡 Suggested Commands:")
        for s in data["suggestions"]:
            cmd = s.get("command", "<no command>")
            raw = s.get("text", "")

            # extract only the DESCRIPTION cleanly
            desc = ""
            if "DESCRIPTION:" in raw:
                parts = raw.split("DESCRIPTION:", 1)
                desc = parts[1].strip()

            lines.append(f" • {cmd} — {desc}")

        lines.append("")

    return "\n".join(lines)

class AIShellApp(App):
    """A Textual app for the AI Shell."""

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
        self._updating_from_suggestion = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output_log")
        with Horizontal():
            yield Input(placeholder="Ask me anything...", id="user_input")
            yield Button("🎤 Mic (F2)", id="mic_btn", variant="primary")
            yield Button("➤ Send", id="send_btn", variant="success")
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
        if event.button.id == "mic_btn":
            self.action_toggle_mic()
        elif event.button.id == "send_btn":
            await self.submit_message()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        self.hide_suggestions()
        await self.submit_message()

    async def on_input_changed(self, event: Input.Changed) -> None:
        try:
            if self._updating_from_suggestion:
                self._updating_from_suggestion = False
                return

            if self._autocomplete_debounce and not self._autocomplete_debounce.done():
                try:
                    self._autocomplete_debounce.cancel()
                except Exception:
                    pass

            self._navigating_suggestions = False
            input_value = event.value

            if not input_value.strip():
                self.hide_suggestions()
                return

            async def debounced_autocomplete():
                try:
                    await asyncio.sleep(0.1)
                    current_input = self.query_one("#user_input", Input).value
                    if current_input.strip() and current_input == input_value:
                        await self.update_autocomplete_suggestions(input_value)
                except Exception:
                    pass

            self._autocomplete_debounce = asyncio.create_task(debounced_autocomplete())
        except Exception:
            pass

    async def submit_message(self) -> None:
        self.hide_suggestions()
        self._navigating_suggestions = False

        input_box = self.query_one("#user_input", Input)
        user_input = input_box.value
        output_log = self.query_one("#output_log", Log)

        if not user_input.strip():
            return

        clean_input = user_input.strip()
        lower = clean_input.lower()

        # Exit
        if lower in ["exit", "quit"]:
            output_log.write_line("Exiting application...")
            self.exit()
            return

        # Show request
        input_box.clear()
        output_log.write_line(f"\n> Your request: '{user_input}'")

        # -------- RAG Detection --------
        rag_question = None
        if lower.startswith("rag "):
            rag_question = clean_input[4:].strip()
        elif lower.startswith("? "):
            rag_question = clean_input[2:].strip()
        elif clean_input.endswith("?"):
            rag_question = clean_input

        if rag_question:
            ensure_vectorstore(rebuild=False)
            answer_text = rag_answer(rag_question)
            output_log.write_line("\n📘 RAG Answer:")
            output_log.write_line(format_rag_dict(answer_text))
            input_box.focus()
            return

        # -------- Normal Command Handling --------
        command_to_run = get_smart_command(user_input)
        output_log.write_line(f"🤖 My interpretation: Executing '{command_to_run}'")

        result = execute_command(command_to_run)
        output_log.write_line(result)

        if len(result) < 200:
            self.run_worker(lambda: self.voice_engine.speak(result), thread=True)
        else:
            self.run_worker(lambda: self.voice_engine.speak("Command executed. Output is displayed above."), thread=True)

        input_box.focus()

    async def update_autocomplete_suggestions(self, text: str) -> None:
        try:
            suggestions = await suggest(text, limit=6)
            suggestion_list = self.query_one("#suggestion_list", SuggestionList)
            suggestion_container = self.query_one("#suggestion_container", Container)

            if suggestions:
                suggestion_list.update_suggestions(suggestions)
                suggestion_container.display = True
                suggestion_container.refresh()
            else:
                self.hide_suggestions()
        except Exception:
            self.hide_suggestions()

    def hide_suggestions(self) -> None:
        try:
            suggestion_container = self.query_one("#suggestion_container", Container)
            suggestion_list = self.query_one("#suggestion_list", SuggestionList)
            suggestion_container.display = False
            suggestion_list.hide()
            suggestion_container.refresh()
        except Exception:
            pass

    def on_suggestion_list_selected(self, event: SuggestionList.Selected) -> None:
        try:
            input_box = self.query_one("#user_input", Input)
            self._updating_from_suggestion = True
            input_box.value = event.suggestion
            self.hide_suggestions()
            input_box.focus()
            self._navigating_suggestions = False
        except Exception:
            pass

    async def on_key(self, event: events.Key) -> None:
        try:
            input_box = self.query_one("#user_input", Input)
            suggestion_list = self.query_one("#suggestion_list", SuggestionList)
            suggestion_container = self.query_one("#suggestion_container", Container)

            if suggestion_container.display and suggestion_list._visible:
                option_count = len(suggestion_list._suggestions)

                if event.key == "down":
                    if not suggestion_list.has_focus:
                        self._navigating_suggestions = True
                        suggestion_list.focus()
                        if option_count > 0:
                            suggestion_list.highlighted = 0
                        event.prevent_default()
                    return

                elif event.key == "up":
                    if not suggestion_list.has_focus:
                        self._navigating_suggestions = True
                        suggestion_list.focus()
                        if option_count > 0:
                            suggestion_list.highlighted = option_count - 1
                        event.prevent_default()
                    return

                elif event.key == "escape":
                    self.hide_suggestions()
                    input_box.focus()
                    self._navigating_suggestions = False
                    event.prevent_default()
                    return
        except Exception:
            pass

    def action_toggle_mic(self) -> None:
        input_box = self.query_one("#user_input", Input)
        input_box.placeholder = "🎤 Listening... Speak now!"
        input_box.disabled = True
        self.run_worker(self.listen_worker, exclusive=True, thread=True)

    
    def listen_worker(self) -> None:
        text = self.voice_engine.listen()
        self.call_from_thread(self.on_listen_finished, text)

    def on_listen_finished(self, text: str) -> None:
        input_box = self.query_one('#user_input', Input)
        input_box.disabled = False
        input_box.placeholder = 'Ask me anything...'

        if text:
            input_box.value = text
            input_box.focus()
            self.post_message(Input.Changed(input_box, text))
        else:
            self.query_one('#output_log', Log).write_line('❌ Could not hear anything. Try again.')
            input_box.focus()