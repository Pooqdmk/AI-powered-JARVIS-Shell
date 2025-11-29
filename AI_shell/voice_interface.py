# ai_shell/voice_interface.py
import speech_recognition as sr
import pyttsx3

class VoiceInterface:
    def __init__(self):
        # Initialize the recognizer and the TTS engine
        self.recognizer = sr.Recognizer()
        self.engine = pyttsx3.init()
        
        # Configure TTS voice (optional: select a specific voice)
        voices = self.engine.getProperty('voices')
        # On Windows, voices[0] is usually male, voices[1] is female
        if len(voices) > 1:
            self.engine.setProperty('voice', voices[1].id) 
        self.engine.setProperty('rate', 170) # Speed of speech

    def listen(self) -> str:
        """
        Listens to the microphone and returns the transcribed text.
        Returns None if nothing was understood.
        """
        with sr.Microphone() as source:
            print("🎤 Listening... (Speak now)")
            # Adjust for ambient noise (crucial for accuracy)
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            
            try:
                # Listen for audio input
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                print("⏳ Recognizing...")
                # Use Google's free STT API (online)
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
                print(f"❌ Could not request results; {e}")
                return None
            except Exception as e:
                print(f"❌ Error: {e}")
                return None

    def speak(self, text: str):
        """
        Converts text to spoken audio.
        """
        if text:
            self.engine.say(text)
            self.engine.runAndWait()

# For testing independently
if __name__ == "__main__":
    vi = VoiceInterface()
    vi.speak("Voice interface initialized. Say something.")
    result = vi.listen()
    if result:
        vi.speak(f"You said: {result}")