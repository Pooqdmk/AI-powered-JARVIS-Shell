# ai_shell/voice_interface.py

import speech_recognition as sr
import pyttsx3
import threading


class VoiceInterface:
    def __init__(self):
        # Initialize STT and TTS engines
        self.recognizer = sr.Recognizer()
        self.engine = pyttsx3.init()

        # 🔒 Add a thread lock to prevent runAndWait() crash
        self.lock = threading.Lock()

        # Configure TTS voice (optional)
        voices = self.engine.getProperty("voices")
        if len(voices) > 1:
            self.engine.setProperty("voice", voices[1].id)  # Female voice
        self.engine.setProperty("rate", 170)

    def listen(self) -> str | None:
        """
        Listens to the microphone and returns text.
        Returns None on failure.
        """
        with sr.Microphone() as source:
            print("🎤 Listening... (Speak now)")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

            try:
                audio = self.recognizer.listen(
                    source, timeout=5, phrase_time_limit=10
                )

                print("⏳ Recognizing...")
                text = self.recognizer.recognize_google(audio)
                print(f"🗣️ You said: {text}")
                return text

            except sr.WaitTimeoutError:
                print("❌ No speech detected.")
                return None
            except sr.UnknownValueError:
                print("❌ Could not understand audio.")
                return None
            except sr.RequestError as e:
                print(f"❌ Request error: {e}")
                return None
            except Exception as e:
                print(f"❌ Error: {e}")
                return None

    def speak(self, text: str):
        """
        Thread-safe TTS speaking function.
        REQUIRED to avoid `run loop already started` crash.
        """
        if not text:
            return

        # Ensure only one thread uses pyttsx3 at a time
        with self.lock:
            self.engine.say(text)
            self.engine.runAndWait()


# For standalone testing
if __name__ == "__main__":
    vi = VoiceInterface()
    vi.speak("Voice interface initialized. Say something.")
    result = vi.listen()
    if result:
        vi.speak(f"You said: {result}")
