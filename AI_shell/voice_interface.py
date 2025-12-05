# ai_shell/voice_interface.py
import speech_recognition as sr
import pyttsx3
import threading

class VoiceInterface:
    def __init__(self):
        # Initialize the recognizer and the TTS engine
        self.recognizer = sr.Recognizer()
        try:
            self.engine = pyttsx3.init()
            # Configure TTS voice (optional: select a specific voice)
            voices = self.engine.getProperty('voices')
            # On Windows, voices[0] is usually male, voices[1] is female
            if len(voices) > 1:
                self.engine.setProperty('voice', voices[1].id) 
            self.engine.setProperty('rate', 170) # Speed of speech
        except Exception:
            # TTS initialization failed, but we can still do speech recognition
            self.engine = None

    def listen(self) -> str:
        """Listens to the microphone and returns the transcribed text."""
        # Removed print statements - messages will be shown in TUI instead
        with sr.Microphone() as source:
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                text = self.recognizer.recognize_google(audio)
                return text
            except sr.WaitTimeoutError:
                # Return empty string instead of None for consistency
                return ""
            except sr.UnknownValueError:
                return ""
            except sr.RequestError:
                return ""
            except Exception:
                return ""

    def speak(self, text: str):
        """Converts text to spoken audio in a separate thread to avoid asyncio conflicts."""
        if text and self.engine:
            try:
                threading.Thread(target=self._speak_thread, args=(text,), daemon=True).start()
            except Exception:
                # Silently fail if TTS can't be started
                pass

    def _speak_thread(self, text: str):
        """Internal thread function for TTS."""
        try:
            if self.engine:
                self.engine.say(text)
                self.engine.runAndWait()
        except Exception:
            # Silently fail if TTS encounters an error
            pass

# For testing independently
if __name__ == "__main__":
    vi = VoiceInterface()
    vi.speak("Voice interface initialized. Say something.")
    result = vi.listen()
    if result:
        vi.speak(f"You said: {result}")