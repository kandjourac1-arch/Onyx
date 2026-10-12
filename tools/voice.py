"""
Onyx V2 - Module Vocal (tools/voice.py)
Pont vers VoiceAssistant (openwakeword, sounddevice, faster-whisper, pyttsx3, scipy)
"""

import threading
from .voice_engine import VoiceAssistant, TTSEngine, STTEngine, CleanTextForTTS

class VoiceEngine:
    """Classe de compatibilité pour les modules existants."""
    def __init__(self, rate: int = 175, volume: float = 1.0):
        self.tts_engine = TTSEngine(rate=rate, volume=volume)
        self.stt_engine = STTEngine()

    def speak(self, text: str):
        """Synthèse vocale hors-ligne dans un thread séparé avec pyttsx3."""
        self.tts_engine.speak(text)

    def listen(self, timeout: int = 5) -> str:
        """Capture et transcrit la voix localement."""
        try:
            import sounddevice as sd
            import numpy as np
            sample_rate = 16000
            print("[VoiceEngine] Écoute locale...")
            audio = sd.rec(int(timeout * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
            sd.wait()
            return self.stt_engine.transcribe(audio.flatten(), sample_rate=sample_rate, language="fr")
        except Exception as e:
            print(f"[VoiceEngine] Erreur écoute : {e}")
            return ""

__all__ = ["VoiceEngine", "VoiceAssistant", "TTSEngine", "STTEngine"]