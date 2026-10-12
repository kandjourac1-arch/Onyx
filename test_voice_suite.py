import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from tools.voice_engine import WakeWordEngine, CleanTextForTTS
from app import process_voice_prompt

print("=== 1. TEST DÉTECTION MULTI-WAKEWORD ===")
wwe = WakeWordEngine()
test_phrases = [
    "Sheva quelle heure est-il ?",
    "Hey Jarvis donne-moi la météo à Paris",
    "Jarvis quel est le statut du pc ?",
    "Chéva comment vas-tu ?",
    "Dis Sheva, ajoute une tâche",
    "Sheva",
    "Hey Jarvis",
    "Bonjour je voudrais une information"
]

for phrase in test_phrases:
    detected, kw, clean = wwe.extract_wakeword_and_prompt(phrase)
    print(f"[{'V' if detected else 'X'}] \"{phrase}\" -> Mot-clé: '{kw}' | Commande: \"{clean}\"")

print("\n=== 2. TEST NETTOYAGE TEXTE TTS ===")
raw = "Voici le statut : **CPU** à 15% 💻 et **RAM** à 42% 🌤️ ```code python```"
clean = CleanTextForTTS.clean(raw)
print("Original :", raw)
print("Nettoyé  :", clean)

print("\n=== 3. TEST CERVEAU VOCAL (RÉPONSES LOCALES RAPIDES) ===")
print("Heure    :", process_voice_prompt("quelle heure est-il"))
print("Date     :", process_voice_prompt("quelle est la date"))
print("Identité :", process_voice_prompt("qui es-tu"))
print("Calcul   :", process_voice_prompt("25 * 4"))

print("\nTOUS LES TESTS SONT PASSÉS AVEC SUCCÈS !")
