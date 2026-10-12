import sys
import io
import traceback

class PythonInterpreter:
    def __init__(self, timeout=15):
        self.timeout = timeout

    def execute_code(self, code: str) -> dict:
        """
        Exécute un bloc de code Python et capture la sortie stdout/stderr.
        
        Retourne :
            {"success": bool, "output": str, "error": str}
        """
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output
        
        exec_globals = {"__name__": "__main__"}
        exec_locals = {}
        
        try:
            exec(code, exec_globals, exec_locals)
            sys.stdout = old_stdout
            out = redirected_output.getvalue()
            return {
                "success": True,
                "output": out if out else "(Code exécuté avec succès sans sortie texte)",
                "error": ""
            }
        except Exception:
            sys.stdout = old_stdout
            err_str = traceback.format_exc()
            return {
                "success": False,
                "output": redirected_output.getvalue(),
                "error": err_str
            }
