import os


class FileAgent:
    def __init__(self):
        pass

    def read_file(self, path: str) -> dict:
        """
        Lit le contenu d'un fichier texte donné.
        
        Retourne :
            {"success": bool, "path": str, "content": str, "error": str}
        """
        clean_path = path.strip("'\"")
        
        if not os.path.exists(clean_path):
            return {
                "success": False,
                "path": clean_path,
                "content": "",
                "error": f"Le fichier '{clean_path}' n'existe pas."
            }
        
        if not os.path.isfile(clean_path):
            return {
                "success": False,
                "path": clean_path,
                "content": "",
                "error": f"Le chemin '{clean_path}' n'est pas un fichier valide."
            }
            
        try:
            with open(clean_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "success": True,
                "path": clean_path,
                "content": content,
                "error": ""
            }
        except Exception as e:
            return {
                "success": False,
                "path": clean_path,
                "content": "",
                "error": str(e)
            }
