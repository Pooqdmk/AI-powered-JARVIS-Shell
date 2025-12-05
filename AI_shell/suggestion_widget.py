# ai_shell/suggestion_widget.py
"""
Custom widget for displaying autocomplete suggestions in a dropdown list.
Compatible with Textual 6.6.0.
"""

from textual.widgets import OptionList
from textual.widget import Widget
from textual.message import Message
from textual import events


class SuggestionList(OptionList):
    """
    A dropdown list widget for displaying autocomplete suggestions.
    Extends OptionList for keyboard navigation support.
    """
    
    DEFAULT_CSS = """
    SuggestionList {
        height: auto;
        max-height: 10;
        border: solid $primary;
        background: $surface;
        display: none;
        layer: suggestions;
    }
    
    SuggestionList:focus {
        border: solid $accent;
    }
    """
    
    class Selected(Message):
        """Message sent when a suggestion is selected."""
        def __init__(self, suggestion: str) -> None:
            self.suggestion = suggestion
            super().__init__()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._visible = False
        self._suggestions: list[str] = []  # Store suggestions for easy access
    
    def show(self) -> None:
        """Show the suggestion list."""
        self.display = True
        self._visible = True
    
    def hide(self) -> None:
        """Hide the suggestion list."""
        self.display = False
        self._visible = False
    
    def update_suggestions(self, suggestions: list[str]) -> None:
        """Update the list of suggestions."""
        try:
            self.clear_options()
            # Ensure we handle None, empty list, or list with only empty strings
            if not suggestions or not any(s.strip() if s else False for s in suggestions):
                self._suggestions = []
                self.hide()
                return
            
            self._suggestions = [s for s in suggestions if s and s.strip()].copy()
            if self._suggestions:
                for suggestion in self._suggestions:
                    self.add_option(suggestion)
                self.show()
                # Force refresh to ensure visibility
                self.refresh()
                # Also refresh parent container
                if self.parent:
                    self.parent.refresh()
            else:
                self.hide()
        except Exception:
            # Silently handle errors - just hide the widget
            self.hide()
    
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection of a suggestion."""
        try:
            if event.option_index is not None and 0 <= event.option_index < len(self._suggestions):
                option_text = self._suggestions[event.option_index]
                self.post_message(self.Selected(option_text))
                self.hide()
        except Exception:
            # Silently handle any errors
            pass
    
    def on_key(self, event: events.Key) -> None:
        """Handle keyboard events for navigation."""
        try:
            if event.key == "escape":
                self.hide()
                event.prevent_default()
                # Return focus to input
                try:
                    self.app.query_one("#user_input").focus()
                except Exception:
                    pass
            elif event.key == "enter":
                # Select the highlighted option
                highlighted = self.highlighted
                if highlighted is not None and 0 <= highlighted < len(self._suggestions):
                    option_text = self._suggestions[highlighted]
                    self.post_message(self.Selected(option_text))
                    self.hide()
                event.prevent_default()
            else:
                # Let OptionList handle arrow keys
                super().on_key(event)
        except Exception:
            # Silently handle any errors
            pass

