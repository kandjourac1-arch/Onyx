# brain/sphinx_engine.py
"""
Sphinx Engine - Orchestrateur du système Sphinx Duo
Rôle : Intègre les actions d'écriture ET d'importation de fichiers dans la boucle agentique.
"""

from typing import Dict, Any, Tuple
from .sphinx_right import SphinxRight
from .sphinx_left import SphinxLeft

class SphinxDuoSystem:

    def __init__(self):
        self.right = SphinxRight()
        self.left = SphinxLeft()

    def inspect_and_prepare_request(self, user_input: str) -> Tuple[Dict[str, Any], str]:
        intent_info = self.right.analyze_intent(user_input)
        enriched_prompt = user_input

        if intent_info.get("action_os") == "READ_FILE":
            target_path = intent_info.get("target_path")
            read_result = self.left.execute_physical_read(target_path)
            if read_result["success"]:
                print(f"[Sphinx Left 📥] {read_result['message']}")
                enriched_prompt = (
                    f"--- DEBUT FICHIER IMPORTE ({read_result['file_path']}) ---\n"
                    f"{read_result['content']}\n"
                    f"--- FIN FICHIER IMPORTE ---\n\n"
                    f"Consigne utilisateur : {user_input}"
                )
            else:
                print(f"[Sphinx Left ⚠️] {read_result['message']}")
                enriched_prompt = f"[Note Système: {read_result['message']}]\nConsigne : {user_input}"

        return intent_info, enriched_prompt

    def process_and_guard(self, raw_llm_output: str, intent_info: Dict[str, Any]) -> str:
        content_type = intent_info.get("content_type", "TEXT")
        cleaned_output = self.left.purge_hallucinations(raw_llm_output, content_type)
        pure_content = self.left.extract_content(cleaned_output, content_type)

        if content_type == "CODE":
            is_valid, linter_errs = self.left.check_code_quality(pure_content)
            if not is_valid:
                print(f"[Sphinx Left ⚠️] Problème syntaxique détecté : {linter_errs}")

        if intent_info.get("action_os") == "CREATE_FILE_DESKTOP" and intent_info.get("target_path"):
            result_write = self.left.execute_physical_write(
                target_dir=intent_info["target_path"],
                filename=intent_info["suggested_filename"],
                content=pure_content
            )
            if result_write["success"]:
                format_block = "```python" if content_type == "CODE" else "```"
                return (
                    f"✅ **Action accomplie par Sphinx Duo**\n\n"
                    f"Le fichier `{intent_info['suggested_filename']}` a été généré et écrit sur le Bureau :\n"
                    f"`{result_write['file_path']}`\n\n"
                    f"{format_block}\n{pure_content}\n```"
                )
            else:
                return f"❌ Échec d'écriture : {result_write['message']}"

        if content_type == "CODE":
            return f"```python\n{pure_content}\n```"
        else:
            return pure_content