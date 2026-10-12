"""
tools/algorithms/code_analyzer.py
Analyseur de code Python & Assistance au DCL Engine
"""

import ast
import re

class CodeAnalyzer:
    def calculate_cyclomatic_complexity(self, code_source: str) -> int:
        """1. Calculateur de complexité cyclomatique."""
        try:
            tree = ast.parse(code_source)
            complexity = 1
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.With, ast.Assert)):
                    complexity += 1
                elif isinstance(node, ast.BoolOp):
                    complexity += len(node.values) - 1
            return complexity
        except Exception:
            return -1

    def detect_dead_code(self, code_source: str) -> list[str]:
        """2. Détecteur de code mort (fonctions jamais appelées)."""
        warnings = []
        try:
            tree = ast.parse(code_source)
            defined_funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
            called_funcs = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        called_funcs.add(node.func.id)
            
            unused = defined_funcs - called_funcs
            for u in unused:
                if not u.startswith("__") and u != "main":
                    warnings.append(f"Fonction potentiellement non utilisée: '{u}'")
        except Exception as e:
            warnings.append(f"Erreur d'analyse AST: {e}")
        return warnings

    def build_dependency_graph(self, code_source: str) -> dict:
        """3. Générateur de graphe d'importations et de dépendances."""
        imports = []
        try:
            tree = ast.parse(code_source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(f"{node.module}")
        except Exception:
            pass
        return {"imports": list(set(imports))}

    def infer_types(self, code_source: str) -> dict:
        """4. Inférence des signatures de fonctions et types annotés."""
        signatures = {}
        try:
            tree = ast.parse(code_source)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args]
                    signatures[node.name] = {
                        "args": args,
                        "has_return": any(isinstance(n, ast.Return) for n in ast.walk(node))
                    }
        except Exception:
            pass
        return signatures

    def security_scanner(self, code_source: str) -> list[str]:
        """5. Scanner de sécurité basique (eval, exec, hardcoded secrets)."""
        alerts = []
        if re.search(r'\beval\(', code_source):
            alerts.append("CRITIQUE: Utilisation de eval() détectée.")
        if re.search(r'\bexec\(', code_source):
            alerts.append("AVERTISSEMENT: Utilisation de exec() détectée.")
        if re.search(r'(api_key|password|secret)\s*=\s*[\'"][^\'"]+[\'"]', code_source, re.IGNORECASE):
            alerts.append("ATTENTION: Clé d'API ou mot de passe en dur détecté.")
        if re.search(r'\bsubprocess\.run\(.*shell\s*=\s*True', code_source):
            alerts.append("AVERTISSEMENT: subprocess avec shell=True (risque d'injection).")
        return alerts

    def suggest_refactoring(self, code_source: str) -> list[str]:
        """6. Suggestions de refactorisation simples."""
        suggestions = []
        lines = code_source.split('\n')
        if len(lines) > 200:
            suggestions.append("Fichier long (> 200 lignes): Envisager la modularisation.")
        
        complexity = self.calculate_cyclomatic_complexity(code_source)
        if complexity > 10:
            suggestions.append(f"Complexité cyclomatique élevée ({complexity}): Simplifier les conditions.")
            
        return suggestions

    def generate_docstring_template(self, func_name: str, args: list[str]) -> str:
        """7. Générateur de docstrings Sphinx/Google."""
        args_doc = "\n    ".join([f"{arg}: Description de {arg}" for arg in args])
        return f'"""\nDescription de {func_name}.\n\nArgs:\n    {args_doc}\n\nReturns:\n    Description du retour.\n"""'

    def generate_basic_unit_tests(self, code_source: str) -> str:
        """8. Générateur de squelette de unit-tests pytest."""
        types = self.infer_types(code_source)
        test_code = "import pytest\n\n"
        for func, info in types.items():
            if not func.startswith("_"):
                args_dummy = ", ".join(["None"] * len(info["args"]))
                test_code += f"def test_{func}():\n    # TODO: Configurer les entrées\n    # result = {func}({args_dummy})\n    pass\n\n"
        return test_code

    def profile_code_execution(self, code_source: str) -> dict:
        """9. Profiling d'exécution de code léger."""
        import time
        start_t = time.time()
        try:
            compiled = compile(code_source, "<string>", "exec")
            exec_time = time.time() - start_t
            return {"status": "valid", "compile_time_sec": exec_time}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def detect_code_duplication(self, code_source: str) -> float:
        """10. Détecteur de lignes dupliquées."""
        lines = [l.strip() for l in code_source.split('\n') if l.strip() and not l.strip().startswith('#')]
        if not lines:
            return 0.0
        unique_lines = set(lines)
        dup_ratio = 1.0 - (len(unique_lines) / len(lines))
        return round(dup_ratio, 2)
