# Onyx V2 🌌

Onyx V2 est un assistant IA local modulaire combinant des moteurs d'orchestration Python avancés, des extensions natives en Rust pour la performance, et une interface moderne.

---

## 🚀 Fonctionnalités Principales

- **Moteur Agentique Avancé** : Routage dynamique, mémoires STM/LTM, architecture d'agents spécialisés.
- **Accélération Rust** : Modules natifs PyO3 haute performance (onyx_rust).
- **Interfaces Multiples** :
  - Mode Terminal interactif.
  - Mode Web / Serveur applicatif (onyx_app.server / onyx_next).
- **Outils & Services Intégrés** : Diagnostic, synthèse & reconnaissance vocale (Sherpa-ONNX), intégration de messagerie, monitoring système.

---

## 🛠️ Installation & Prérequis

### Prérequis
- Python 3.11+
- Rust & Cargo (optionnel, pour compiler les bindings natifs)
- Node.js & npm (pour l'interface frontend onyx_next/ui)

### Installation des dépendances Python

`ash
python -m venv .venv
# Sur Windows :
.venv\Scripts\activate
# Sur Linux / macOS :
source .venv/bin/activate

pip install -r requirements.txt
`

---

## ⚙️ Configuration

Copiez les fichiers de configuration d'exemple :

`ash
cp mail.env.example mail.env
cp model.env.example model.env
`

Renseignez vos endpoints de modèles locaux (ex: LM Studio, Ollama) et vos paramètres de messagerie si nécessaire.

---

## 🚦 Démarrage

### Lancer Onyx V2

`ash
# Lancement combiné (Web en arrière-plan + Terminal) :
python app.py

# Lancement en mode Terminal uniquement :
python app.py --terminal

# Lancement en mode Web uniquement :
python app.py --web
`

---

## 🧪 Tests & Qualité de code

`ash
pytest
ruff check app.py brain services tests
mypy services brain --ignore-missing-imports
`
