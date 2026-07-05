"""Background QThread workers for voice I/O.

Everything that touches the microphone, network speech recognition, or the
TTS engine runs off the Qt UI thread so the orb never freezes mid-animation.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

try:
    import speech_recognition as sr
except ImportError:  # surfaced as a friendly error at runtime instead of crashing import
    sr = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


class ListenOnceWorker(QThread):
    """Listens for a single phrase and emits the recognized text."""

    result = Signal(str)
    error = Signal(str)
    started_listening = Signal()

    def run(self) -> None:
        if sr is None:
            self.error.emit(
                "speech_recognition isn't installed. Run: pip install SpeechRecognition pyaudio"
            )
            return
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
                self.started_listening.emit()
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=12)
        except sr.WaitTimeoutError:
            self.error.emit("Didn't hear anything.")
            return
        except (OSError, AttributeError, ImportError) as exc:
            self.error.emit(
                "Couldn't access the microphone. If you just installed this, PyAudio "
                f"may not have installed correctly ({exc}). Try: pip install pyaudio "
                "(Linux: sudo apt install portaudio19-dev first)."
            )
            return

        try:
            text = recognizer.recognize_google(audio)
            self.result.emit(text)
        except sr.UnknownValueError:
            self.error.emit("Couldn't make out what you said.")
        except sr.RequestError as exc:
            self.error.emit(f"Speech recognition service error: {exc}")


class WakeWordWorker(QThread):
    """Continuously listens in the background for a wake word.

    Emits `wake_detected(remainder)` where `remainder` is any speech captured
    right after the wake word in the same phrase (may be empty, in which case
    the caller should prompt for / capture a follow-up command).
    """

    wake_detected = Signal(str)
    error = Signal(str)
    listening_state = Signal(bool)  # True while actively capturing a phrase

    def __init__(self, wake_word: str = "jarvis", parent=None):
        super().__init__(parent)
        self.wake_word = wake_word.lower()
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        if sr is None:
            self.error.emit(
                "speech_recognition isn't installed. Run: pip install SpeechRecognition pyaudio"
            )
            return
        recognizer = sr.Recognizer()
        try:
            mic = sr.Microphone()
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
        except (OSError, AttributeError, ImportError) as exc:
            self.error.emit(
                "Couldn't access the microphone. If you just installed this, PyAudio "
                f"may not have installed correctly ({exc}). Try: pip install pyaudio "
                "(Linux: sudo apt install portaudio19-dev first)."
            )
            return

        while self._running:
            try:
                with mic as source:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
            except sr.WaitTimeoutError:
                continue
            except (OSError, AttributeError) as exc:
                self.error.emit(f"Microphone error: {exc}")
                return

            if not self._running:
                break

            try:
                text = recognizer.recognize_google(audio)
            except (sr.UnknownValueError, sr.RequestError):
                continue

            lower = text.lower()
            if self.wake_word in lower:
                idx = lower.index(self.wake_word)
                remainder = text[idx + len(self.wake_word):].strip(" ,.:")
                self.wake_detected.emit(remainder)


class SpeakWorker(QThread):
    """Speaks a line of text aloud via pyttsx3 (offline TTS)."""

    finished = Signal()
    error = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self) -> None:
        if pyttsx3 is None:
            self.error.emit("pyttsx3 isn't installed. Run: pip install pyttsx3")
            return
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 178)
            engine.say(self.text)
            engine.runAndWait()
            engine.stop()
        except Exception as exc:  # pyttsx3 backends raise assorted platform errors
            self.error.emit(f"TTS error: {exc}")
            return
        self.finished.emit()
