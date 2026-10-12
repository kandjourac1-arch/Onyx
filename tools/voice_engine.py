"""
Onyx V2 - Moteur Vocal 100% Local & Open-Source
- Détection multi-mots-clés simultanée : 'sheva' ET 'hey_jarvis' (ainsi que 'jarvis')
- OpenWakeWord natif pour 'hey_jarvis' + Détection VAD/Whisper haute précision pour 'sheva'
- Capture et traitement audio adaptatif (sounddevice + scipy)
- Ring buffer audio pré-roll (zéro perte de début de mot)
- Transcription vocale hors-ligne (faster-whisper) avec extraction directe de commande
- Synthèse vocale hors-ligne (pyttsx3) avec voix française Hortense prioritaire
- Protection anti-écho (le micro n'écoute pas la propre voix de l'IA)
- Intégration SocketIO & Cerveau Onyx
"""

import os
import re
import sys
import time
import math
import queue
import logging
import threading
import unicodedata
from collections import deque
import numpy as np

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OnyxVoice")

# Dépendances optionnelles avec fallbacks sécurisés
try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    logger.warning("[OnyxVoice] 'sounddevice' n'est pas installé.")

try:
    import scipy.io.wavfile as wavfile
    import scipy.signal as signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("[OnyxVoice] 'scipy' n'est pas installé.")

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except Exception as e:
    WHISPER_AVAILABLE = False
    logger.warning(f"[OnyxVoice] 'faster-whisper' indisponible: {e}")

try:
    import openwakeword
    from openwakeword.model import Model as OpenWakeWordModel
    OWW_AVAILABLE = True
except ImportError:
    OWW_AVAILABLE = False
    logger.warning("[OnyxVoice] 'openwakeword' n'est pas installé.")

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    logger.warning("[OnyxVoice] 'pyttsx3' n'est pas installé.")


class CleanTextForTTS:
    @staticmethod
    def clean(text: str) -> str:
        """Nettoie le texte (markdown, code, URLs, emojis, symboles) pour une prononciation naturelle."""
        if not text:
            return ""
        # Remplacer les blocs de code par une indication orale
        text = re.sub(r'```[a-zA-Z]*[\s\S]*?```', ' Voici les détails du code. ', text)
        # Supprimer le code en ligne
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Supprimer les liens markdown [texte](url)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Supprimer les URLs brutes
        text = re.sub(r'https?://\S+', '', text)
        # Supprimer les titres markdown (#, ##, ###)
        text = re.sub(r'#+\s*', '', text)
        # Supprimer les puces et symboles de listes
        text = re.sub(r'^\s*[-*+•]\s+', '', text, flags=re.MULTILINE)
        # Supprimer les caractères de mise en gras / italique
        text = re.sub(r'[*_~]', '', text)
        # Remplacer les % par 'pourcent'
        text = re.sub(r'(\d+)\s*%', r'\1 pour cent', text)
        # Supprimer les emojis et caractères non-ASCII problématiques pour SAPI5
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        text = re.sub(r'[^\w\s.,;:!?\'"()\-\/%€$°+]', ' ', text)
        # Remplacer les retours à la ligne multiples par des pauses de phrase
        text = re.sub(r'\n+', '. ', text)
        # Nettoyer les espaces superflus
        text = re.sub(r'\s+', ' ', text).strip()
        return text


class TTSEngine:
    """Gestionnaire de synthèse vocale hors-ligne via pyttsx3 avec worker thread dédié."""
    def __init__(self, rate: int = 175, volume: float = 1.0, voice_index: int = 0):
        self.rate = rate
        self.volume = volume
        self.voice_index = voice_index
        self._queue = queue.Queue()
        self._is_speaking = False
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _init_engine(self):
        if not PYTTSX3_AVAILABLE:
            return None
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', self.rate)
            engine.setProperty('volume', self.volume)
            voices = engine.getProperty('voices')
            if voices:
                # Priorité absolue à la voix française (Hortense / Julie / Paul / french)
                fr_voice = next((v for v in voices if 'hortense' in v.name.lower() or 'fr-fr' in v.id.lower() or 'french' in v.name.lower()), None)
                if not fr_voice:
                    fr_voice = next((v for v in voices if 'fr' in v.id.lower() or 'french' in v.name.lower()), None)

                if fr_voice:
                    engine.setProperty('voice', fr_voice.id)
                    logger.info(f"[TTSEngine] Voix française sélectionnée : {fr_voice.name}")
                elif 0 <= self.voice_index < len(voices):
                    engine.setProperty('voice', voices[self.voice_index].id)
            return engine
        except Exception as e:
            logger.error(f"[TTSEngine] Erreur initialisation pyttsx3: {e}")
            return None

    def _worker_loop(self):
        engine = self._init_engine()

        while True:
            try:
                task = self._queue.get()
                if task is None:
                    break
                text, on_start, on_end = task
                clean_text = CleanTextForTTS.clean(text)
                if not clean_text:
                    if on_end:
                        try:
                            on_end()
                        except Exception:
                            pass
                    self._queue.task_done()
                    continue

                self._is_speaking = True
                if on_start:
                    try:
                        on_start()
                    except Exception:
                        pass

                if engine is None:
                    engine = self._init_engine()

                if engine:
                    try:
                        engine.setProperty('rate', self.rate)
                        engine.setProperty('volume', self.volume)
                        engine.say(clean_text)
                        engine.runAndWait()
                    except Exception as e:
                        logger.error(f"[TTSEngine] Erreur lecture: {e}")
                        try:
                            engine = self._init_engine()
                        except Exception:
                            pass

                # Petite pause pour éviter que la coupure audio immédiate n'accroche le micro
                time.sleep(0.15)
                self._is_speaking = False

                if on_end:
                    try:
                        on_end()
                    except Exception:
                        pass
                self._queue.task_done()
            except Exception as e:
                logger.error(f"[TTSEngine] Erreur boucle TTS: {e}")
                self._is_speaking = False

    def speak(self, text: str, on_start=None, on_end=None):
        """Met en file d'attente un texte à lire."""
        self._queue.put((text, on_start, on_end))

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking


class STTEngine:
    """Moteur de transcription locale via faster-whisper."""
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self._load_lock = threading.Lock()

    def load_model(self):
        if not WHISPER_AVAILABLE:
            return False
        with self._load_lock:
            if self.model is None:
                try:
                    logger.info(f"[STTEngine] Chargement du modèle faster-whisper ({self.model_size})...")
                    self.model = WhisperModel(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type
                    )
                    logger.info("[STTEngine] Modèle faster-whisper prêt.")
                    return True
                except Exception as e:
                    logger.error(f"[STTEngine] Erreur chargement faster-whisper: {e}")
                    return False
        return True

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000, language: str = "fr") -> str:
        """Transcrit un tableau numpy float32 normalisé [-1.0, 1.0]."""
        if not self.load_model():
            return ""

        try:
            audio_data = np.asarray(audio_data).flatten()
            if audio_data.size == 0:
                return ""

            if audio_data.dtype != np.float32:
                if audio_data.dtype == np.int16:
                    audio_data = audio_data.astype(np.float32) / 32768.0
                else:
                    audio_data = audio_data.astype(np.float32)

            peak = float(np.max(np.abs(audio_data))) if audio_data.size else 0.0
            if peak > 1.0:
                audio_data = audio_data / peak

            rms = float(np.sqrt(np.mean(audio_data ** 2))) if audio_data.size else 0.0
            if rms < 0.003:
                return ""

            segments, info = self.model.transcribe(
                audio_data,
                beam_size=5,
                language=language,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=150),
                condition_on_previous_text=False,
                temperature=0.0
            )

            text_parts = [segment.text for segment in segments]
            full_text = " ".join(text_parts).strip()
            if full_text:
                logger.info(f"[STTEngine] Transcription ({info.language}, p={info.language_probability:.2f}): {full_text}")
            return full_text
        except Exception as e:
            logger.error(f"[STTEngine] Erreur pendant la transcription: {e}")
            return ""


class WakeWordEngine:
    """
    Moteur de détection combiné :
    - Détection ONNX ultra-rapide pour 'hey_jarvis' via openwakeword
    - Détection textuelle et phonétique pour 'sheva' et 'jarvis'
    """
    def __init__(self, threshold: float = 0.42):
        self.threshold = threshold
        self.oww_model = None
        self.can_detect_openwakeword_jarvis = False

        # Variantes phonétiques de Sheva et Jarvis
        self.sheva_aliases = ["sheva", "cheva", "chéva", "shéva", "sheeva", "shiva", "chiva", "seva", "ceva"]
        self.jarvis_aliases = ["hey jarvis", "hey_jarvis", "jarvis", "jarvice", "djervis", "djarvis", "jervis"]
        self.all_aliases = self.sheva_aliases + self.jarvis_aliases

        self._init_oww()

    def _init_oww(self):
        if not OWW_AVAILABLE:
            return
        try:
            try:
                openwakeword.utils.download_models()
            except Exception:
                pass

            # Chargement de tous les modèles openwakeword disponibles (dont hey_jarvis)
            self.oww_model = OpenWakeWordModel(inference_framework="onnx")
            loaded_models = [name.lower() for name in self.oww_model.models.keys()]
            self.can_detect_openwakeword_jarvis = any("jarvis" in name for name in loaded_models)

            logger.info(f"[WakeWordEngine] openwakeword initialisé. Modèles chargés: {list(self.oww_model.models.keys())}")
            if self.can_detect_openwakeword_jarvis:
                logger.info("[WakeWordEngine] Détection ONNX 'hey_jarvis' activée avec succès.")
            logger.info("[WakeWordEngine] Détection double active: 'sheva' (Whisper-VAD) & 'hey_jarvis' (ONNX+Whisper).")
        except Exception as e:
            logger.error(f"[WakeWordEngine] Erreur initialisation openwakeword: {e}")

    def predict_oww(self, audio_chunk_16k_int16: np.ndarray) -> tuple[bool, str]:
        """Détecte 'hey_jarvis' sur un chunk PCM 16kHz via OpenWakeWord."""
        if self.oww_model is None or not self.can_detect_openwakeword_jarvis:
            return False, ""

        try:
            if audio_chunk_16k_int16.dtype != np.int16:
                audio_chunk_16k_int16 = (audio_chunk_16k_int16 * 32767).astype(np.int16)

            predictions = self.oww_model.predict(audio_chunk_16k_int16)
            for model_name, score in predictions.items():
                if "jarvis" in model_name.lower() and score >= self.threshold:
                    logger.info(f"[WakeWordEngine] Détection ONNX hey_jarvis (score: {score:.3f})")
                    return True, "hey_jarvis"
        except Exception as e:
            logger.error(f"[WakeWordEngine] Erreur prédiction OWW: {e}")
        return False, ""

    def normalize_text(self, text: str) -> str:
        """Normalise un texte pour comparaison sans accent ni ponctuation."""
        if not text:
            return ""
        text = unicodedata.normalize("NFD", text.lower())
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def extract_wakeword_and_prompt(self, text: str) -> tuple[bool, str, str]:
        """
        Vérifie si le texte contient 'sheva' ou 'hey_jarvis'/'jarvis'.
        Retourne : (détecté?, nom_du_wakeword, commande_utilisateur_restante)
        """
        if not text:
            return False, "", ""

        norm_text = self.normalize_text(text)

        # Motifs pour Sheva
        sheva_pattern = r"\b(?:hey|he|eh|salut|bonjour|dis|ok|allo)?\s*(?:sheva|cheva|cheva|sheeva|shiva|chiva|seva)\b"
        # Motifs pour Jarvis
        jarvis_pattern = r"\b(?:hey|he|eh|salut|bonjour|dis|ok|allo)?\s*(?:jarvis|jarvice|djervis|djarvis|jervis)\b"

        matched_kw = None
        if re.search(sheva_pattern, norm_text):
            matched_kw = "sheva"
        elif re.search(jarvis_pattern, norm_text):
            matched_kw = "hey_jarvis"

        if not matched_kw:
            return False, "", text

        # Nettoyer le texte original en enlevant le mot-clé d'appel et les salutations
        pattern_to_strip = (
            r"^\s*(?:hey|hé|eh|salut|bonjour|dis|ok|allo)?\s*"
            r"(?:sheva|cheva|chéva|shéva|sheeva|shiva|chiva|seva|jarvis|jarvice|djervis|djarvis|jervis)"
            r"[\s,;:!?.-]*"
        )
        cleaned = re.sub(pattern_to_strip, "", text, flags=re.IGNORECASE).strip()

        # Si le mot-clé était répété ou subsiste encore au début
        cleaned = re.sub(pattern_to_strip, "", cleaned, flags=re.IGNORECASE).strip()

        return True, matched_kw, cleaned


class VoiceAssistant:
    """
    Assistant Vocal Intégré Complet Onyx V2 :
    - Détection simultanée de 'sheva' et 'hey_jarvis'
    - Écoute continue avec buffer circulaire (Ring Buffer de 1.5s)
    - Prise en charge des phrases directes ("Sheva quelle heure est-il ?") sans interruption
    - VAD (Voice Activity Detection) adaptatif au bruit ambiant
    - Transcription faster-whisper & Synthèse vocale pyttsx3
    - Émission d'événements SocketIO
    """
    def __init__(
        self,
        socketio=None,
        brain_callback=None,
        wakeword: str = "sheva_or_jarvis",
        sample_rate: int = 16000,
        whisper_model: str = "base",
        tts_rate: int = 175,
        tts_volume: float = 1.0,
        sensitivity: float = 0.42
    ):
        self.socketio = socketio
        self.brain_callback = brain_callback
        self.wakeword = wakeword
        self.sample_rate = sample_rate
        self.sensitivity = sensitivity
        self.chunk_size = 1280  # 80ms à 16kHz

        # Moteurs
        self.tts = TTSEngine(rate=tts_rate, volume=tts_volume)
        self.stt = STTEngine(model_size=whisper_model)
        self.wakeword_engine = WakeWordEngine(threshold=self.sensitivity)

        # Contrôle des threads et états
        self._running = False
        self._paused = False
        self._state = "idle"  # idle, listening, wake_detected, recording, transcribing, thinking, speaking
        self._listen_thread = None
        self._audio_queue = queue.Queue()
        self._state_lock = threading.Lock()

        # Ring buffer circulaire pour conserver les 1.5 secondes précédentes
        self._ring_buffer_maxlen = int(1.5 * self.sample_rate / self.chunk_size)
        self._ring_buffer = deque(maxlen=self._ring_buffer_maxlen)

        # Détection d'énergie dynamique
        self._ambient_noise_floor = 0.005
        self._speech_threshold = 0.015

        logger.info("[VoiceAssistant] Prêt. Écoute conjointe activée : 'Sheva' et 'Hey Jarvis'.")

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, new_state: str, extra_data: dict = None):
        """Met à jour l'état interne et émet un événement SocketIO."""
        with self._state_lock:
            self._state = new_state
        logger.info(f"[VoiceAssistant] État: {new_state}")
        if self.socketio:
            payload = {"status": new_state, "timestamp": time.time()}
            if extra_data:
                payload.update(extra_data)
            try:
                self.socketio.emit("voice_status", payload)
            except Exception as e:
                logger.error(f"[VoiceAssistant] Erreur émission SocketIO: {e}")

    def emit_event(self, event_name: str, data: dict):
        """Émet un événement SocketIO personnalisé."""
        if self.socketio:
            try:
                self.socketio.emit(event_name, data)
            except Exception as e:
                logger.error(f"[VoiceAssistant] Erreur émission {event_name}: {e}")

    def play_feedback_tone(self, tone_type: str = "wake"):
        """Génère un bip sonore agréable avec scipy et sounddevice."""
        if not (SD_AVAILABLE and SCIPY_AVAILABLE):
            return
        def _tone():
            try:
                duration = 0.12
                sr = 16000
                t = np.linspace(0, duration, int(sr * duration), False)
                freq = 880 if tone_type == "wake" else 440
                tone = 0.15 * np.sin(2 * np.pi * freq * t)
                envelope = np.sin(np.pi * np.linspace(0, 1, len(t)))
                audio = (tone * envelope).astype(np.float32)
                sd.play(audio, samplerate=sr)
                sd.wait()
            except Exception:
                pass
        threading.Thread(target=_tone, daemon=True).start()

    def _audio_rms(self, audio_chunk: np.ndarray) -> float:
        if audio_chunk is None:
            return 0.0
        chunk = np.asarray(audio_chunk).astype(np.float32).flatten()
        if chunk.size == 0:
            return 0.0
        if np.max(np.abs(chunk)) > 1.5:
            chunk = chunk / 32768.0
        return float(np.sqrt(np.mean(chunk ** 2)))

    def _update_noise_floor(self, rms: float):
        if rms <= 0:
            return
        self._ambient_noise_floor = (self._ambient_noise_floor * 0.94) + (rms * 0.06)
        self._speech_threshold = min(max(self._ambient_noise_floor * 2.8, 0.012), 0.055)

    def _flush_audio_queue(self):
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _speak_and_wait(self, text: str, timeout: float = 30.0):
        """Lit un texte et attend la fin de l'élocution."""
        tts_done = threading.Event()
        self.tts.speak(text, on_end=lambda: tts_done.set())
        tts_done.wait(timeout=timeout)

    def record_user_speech(self, max_duration: float = 12.0, silence_limit: float = 1.3, prefill_audio: np.ndarray = None) -> np.ndarray:
        """
        Enregistre la voix de l'utilisateur avec coupure automatique au silence.
        """
        if not SD_AVAILABLE:
            return np.zeros(0, dtype=np.float32)

        self.set_state("recording")
        recorded_chunks = []
        chunk_duration = 0.08  # 80ms
        chunk_samples = int(self.sample_rate * chunk_duration)

        silence_start_time = None
        speech_detected = False
        start_time = time.time()
        energy_history = []
        energy_threshold = self._speech_threshold

        if prefill_audio is not None:
            prefill_audio = np.asarray(prefill_audio).astype(np.float32).flatten()
            if prefill_audio.size:
                recorded_chunks.append(prefill_audio)

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='float32', blocksize=chunk_samples) as stream:
                while self._running:
                    # Ne pas enregistrer si l'IA parle
                    if self.tts.is_speaking:
                        time.sleep(0.05)
                        continue

                    chunk, overflow = stream.read(chunk_samples)
                    flattened = chunk.flatten().astype(np.float32)
                    recorded_chunks.append(flattened)

                    rms = self._audio_rms(flattened)

                    if not speech_detected and len(energy_history) < 8:
                        energy_history.append(rms)
                        median_noise = float(np.median(energy_history)) if energy_history else self._ambient_noise_floor
                        energy_threshold = min(max(median_noise * 2.8, self._speech_threshold), 0.055)

                    if rms > energy_threshold:
                        speech_detected = True
                        silence_start_time = None
                        self._speech_threshold = energy_threshold
                    elif speech_detected:
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif (time.time() - silence_start_time) >= silence_limit:
                            logger.info("[VoiceAssistant] Fin de phrase détectée (silence).")
                            break
                    else:
                        self._update_noise_floor(rms)

                    if (time.time() - start_time) >= max_duration:
                        logger.info("[VoiceAssistant] Durée maximale atteinte.")
                        break

            if recorded_chunks:
                full_audio = np.concatenate(recorded_chunks, axis=0)
                peak = float(np.max(np.abs(full_audio))) if full_audio.size else 0.0
                if peak > 0.99:
                    full_audio = full_audio / peak
                return full_audio
            return np.zeros(0, dtype=np.float32)

        except Exception as e:
            logger.error(f"[VoiceAssistant] Erreur enregistrement : {e}")
            return np.zeros(0, dtype=np.float32)

    def process_voice_pipeline(self, detected_kw: str = "sheva", initial_user_text: str = "", extra_prefill_audio: np.ndarray = None):
        """Pipeline complet exécuté suite à la détection de 'sheva' ou 'hey_jarvis'."""
        try:
            self.set_state("wake_detected", {"keyword": detected_kw})
            self.emit_event("voice_wake_detected", {
                "keyword": detected_kw,
                "timestamp": time.time()
            })
            self.play_feedback_tone("wake")
            time.sleep(0.08)

            user_text = initial_user_text.strip()

            # Si l'utilisateur n'a dit QUE le mot-clé sans commande immédiate
            if not user_text:
                greeting = "Oui, je t'écoute." if detected_kw == "sheva" else "Oui, à votre écoute."
                self.set_state("speaking", {"text": greeting})
                self._speak_and_wait(greeting, timeout=5.0)

                # Enregistrement de la question
                audio_data = self.record_user_speech(max_duration=12.0, silence_limit=1.2, prefill_audio=extra_prefill_audio)
                if len(audio_data) < self.sample_rate * 0.35:
                    logger.info("[VoiceAssistant] Audio trop court, retour en veille active.")
                    self.set_state("listening")
                    return

                self.set_state("transcribing")
                user_text = self.stt.transcribe(audio_data, sample_rate=self.sample_rate, language="fr")

            if not user_text:
                logger.info("[VoiceAssistant] Aucune commande reconnue.")
                self.set_state("listening")
                return

            logger.info(f"[VoiceAssistant] Commande reçue : '{user_text}'")
            self.emit_event("voice_transcription", {
                "text": user_text,
                "keyword": detected_kw,
                "timestamp": time.time()
            })

            # Exécution par le Cerveau Onyx
            self.set_state("thinking", {"prompt": user_text})
            response_text = ""

            if self.brain_callback:
                try:
                    response_text = self.brain_callback(user_text)
                except Exception as e:
                    logger.error(f"[VoiceAssistant] Erreur exécution cerveau Onyx: {e}")
                    response_text = "Désolé, une erreur est survenue lors de l'analyse de votre demande."
            else:
                response_text = f"J'ai bien entendu votre demande : {user_text}"

            if not response_text:
                response_text = "C'est bien noté."

            logger.info(f"[VoiceAssistant] Réponse générée : '{response_text[:120]}...'")

            self.emit_event("voice_response", {
                "user_text": user_text,
                "response": response_text,
                "timestamp": time.time()
            })

            # Synthèse vocale de la réponse
            self.set_state("speaking", {"text": response_text})
            self.emit_event("voice_speaking_start", {"text": response_text})

            self._speak_and_wait(response_text, timeout=60.0)
            self.emit_event("voice_speaking_end", {"timestamp": time.time()})

        except Exception as e:
            logger.error(f"[VoiceAssistant] Erreur pipeline vocal: {e}")
        finally:
            self._flush_audio_queue()
            self.set_state("listening")

    def _listen_loop(self):
        """Boucle d'écoute continue en arrière-plan."""
        if not SD_AVAILABLE:
            logger.error("[VoiceAssistant] sounddevice indisponible. Arrêt du thread vocal.")
            return

        logger.info("[VoiceAssistant] Démarrage de l'écoute conjointe : 'Sheva' & 'Hey Jarvis'...")
        self.set_state("listening")

        active_speech_chunks = []
        is_speech_active = False
        silence_count = 0
        chunk_duration = self.chunk_size / float(self.sample_rate)
        max_silence_chunks = max(3, int(0.55 / chunk_duration))
        max_utterance_chunks = int(2.8 / chunk_duration)

        def audio_callback(indata, frames, time_info, status):
            if status:
                pass
            # Ne rien capturer si l'IA est en train de parler
            if not self._paused and self._state == "listening" and not self.tts.is_speaking:
                int16_chunk = (indata[:, 0] * 32767).astype(np.int16)
                self._audio_queue.put(int16_chunk)

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32',
                blocksize=self.chunk_size,
                callback=audio_callback
            ):
                while self._running:
                    try:
                        chunk_int16 = self._audio_queue.get(timeout=0.4)
                    except queue.Empty:
                        continue

                    if self._paused or self._state != "listening" or self.tts.is_speaking:
                        active_speech_chunks = []
                        is_speech_active = False
                        silence_count = 0
                        continue

                    chunk_float = chunk_int16.astype(np.float32) / 32768.0
                    self._ring_buffer.append(chunk_float)

                    # 1. Détection ultra-rapide OpenWakeWord (pour Hey Jarvis)
                    detected_oww, oww_kw = self.wakeword_engine.predict_oww(chunk_int16)
                    if detected_oww:
                        logger.info(f"[VoiceAssistant] Mot-clé détecté via ONNX : {oww_kw}")
                        self._flush_audio_queue()
                        self.process_voice_pipeline(detected_kw=oww_kw, initial_user_text="")
                        active_speech_chunks = []
                        is_speech_active = False
                        silence_count = 0
                        continue

                    # 2. Détection VAD + Whisper en continu (pour Sheva et Hey Jarvis)
                    rms = self._audio_rms(chunk_float)

                    if rms >= self._speech_threshold:
                        if not is_speech_active:
                            # Intégrer les 0.4 dernières secondes du ring buffer pour ne pas rater le début du mot
                            pre_roll = list(self._ring_buffer)[-5:]
                            active_speech_chunks = list(pre_roll)
                            is_speech_active = True
                        active_speech_chunks.append(chunk_float)
                        silence_count = 0
                    elif is_speech_active:
                        active_speech_chunks.append(chunk_float)
                        silence_count += 1
                    else:
                        self._update_noise_floor(rms)

                    # Évaluation quand l'utilisateur a fini un court segment de parole
                    utterance_ready = (
                        is_speech_active and
                        (
                            silence_count >= max_silence_chunks or
                            len(active_speech_chunks) >= max_utterance_chunks
                        )
                    )

                    if utterance_ready:
                        audio_snippet = np.concatenate(active_speech_chunks, axis=0) if active_speech_chunks else np.zeros(0, dtype=np.float32)
                        active_speech_chunks = []
                        is_speech_active = False
                        silence_count = 0

                        # S'il y a au moins 0.35s d'audio
                        if audio_snippet.size >= int(self.sample_rate * 0.35):
                            transcribed = self.stt.transcribe(audio_snippet, sample_rate=self.sample_rate, language="fr")
                            if transcribed:
                                has_kw, kw_found, clean_prompt = self.wakeword_engine.extract_wakeword_and_prompt(transcribed)
                                if has_kw:
                                    logger.info(f"[VoiceAssistant] Mot-clé '{kw_found}' détecté dans : '{transcribed}'")
                                    self._flush_audio_queue()
                                    self.process_voice_pipeline(detected_kw=kw_found, initial_user_text=clean_prompt)

        except Exception as e:
            logger.error(f"[VoiceAssistant] Erreur boucle d'écoute: {e}")
        finally:
            self.set_state("idle")
            logger.info("[VoiceAssistant] Boucle d'écoute terminée.")

    def start(self):
        """Démarre le système vocal en arrière-plan."""
        if self._running:
            return
        self._running = True
        self._paused = False
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        logger.info("[VoiceAssistant] Système vocal démarré.")

    def stop(self):
        """Arrête le système vocal."""
        self._running = False
        self._paused = True
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=2.0)
        self.set_state("idle")
        logger.info("[VoiceAssistant] Système vocal arrêté.")

    def pause(self):
        """Met en pause l'écoute."""
        self._paused = True
        self.set_state("paused")

    def resume(self):
        """Reprend l'écoute."""
        self._paused = False
        self.set_state("listening")

    def toggle(self) -> bool:
        """Bascule entre écoute et pause."""
        if self._paused or not self._running:
            if not self._running:
                self.start()
            else:
                self.resume()
            return True
        else:
            self.pause()
            return False


# Alias de compatibilité
VoiceEngine = VoiceAssistant
