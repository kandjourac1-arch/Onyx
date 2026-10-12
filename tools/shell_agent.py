import os
import subprocess
import platform
import shutil
import threading
import time
import queue
from typing import Optional, Dict, Any


class ShellSession:
    """Agent shell persistant pour l'environnement terminal d'ONYX."""

    def __init__(self, shell_type: str = "auto"):
        self.os_type = platform.system().lower()
        self.shell_type = self._detect_shell(shell_type)
        self.process: Optional[subprocess.Popen] = None
        self.output_queue = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self._stop_reader = False
        self._start_shell()

    def _detect_shell(self, shell_type: str) -> str:
        if shell_type != "auto":
            return shell_type
        return "powershell" if "windows" in self.os_type else "bash"

    def _start_shell(self):
        """Lance le processus shell persistant."""
        if self.shell_type == "powershell":
            cmd = ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "-"]
        elif self.shell_type == "cmd":
            cmd = ["cmd.exe"]
        else:
            cmd = ["bash", "--noediting", "-i"]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            universal_newlines=True
        )

        self._stop_reader = False
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

        # Configurer l'encodage UTF-8 en PowerShell si nécessaire
        if self.shell_type == "powershell":
            self._send_raw("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8")

        self._send_command("", wait_for_prompt=False)

    def _reader_loop(self):
        """Lit stdout en continu et alimente la queue."""
        while not self._stop_reader and self.process and self.process.stdout:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                self.output_queue.put(line)
            except Exception:
                break

    def _send_raw(self, command: str):
        if self.process and self.process.stdin:
            self.process.stdin.write(f"{command}\n")
            self.process.stdin.flush()

    def _send_command(self, command: str, wait_for_prompt: bool = True) -> Dict[str, Any]:
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("Le processus shell est arrêté.")

        marker = "__END_ONYX_CMD__"
        exit_marker = "__EXIT_CODE_ONYX__"

        # Formatage des commandes selon le shell utilisé
        if self.shell_type == "powershell":
            full_cmd = f"{command}; Write-Output '{exit_marker}:'$LASTEXITCODE; Write-Output '{marker}'"
            if not command.strip():
                full_cmd = f"Write-Output '{marker}'"
        else:
            full_cmd = f"{command}; echo {exit_marker}:$?; echo {marker}"
            if not command.strip():
                full_cmd = f"echo {marker}"

        # Vidage des résidus dans la queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

        self._send_raw(full_cmd)

        if not wait_for_prompt:
            return {"output": "", "exit_code": 0, "timed_out": False}

        output_lines = []
        exit_code = None
        timed_out = False
        start_time = time.time()
        timeout = 30  # secondes

        while True:
            if time.time() - start_time > timeout:
                timed_out = True
                break

            try:
                line = self.output_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Capture du code de retour
            if exit_marker in line:
                try:
                    raw_val = line.split(":", 1)[1].strip()
                    if raw_val in ["True", "0"]:
                        exit_code = 0
                    elif raw_val == "False":
                        exit_code = 1
                    else:
                        exit_code = int(raw_val)
                except ValueError:
                    exit_code = -1
                continue

            if marker in line:
                break

            output_lines.append(line)

        if timed_out:
            self._kill_shell()
            self._start_shell()  # Relance une session propre après interruption
            return {
                "output": "".join(output_lines),
                "exit_code": -1,
                "timed_out": True
            }

        full_output = "".join(output_lines).strip()
        return {
            "output": full_output,
            "exit_code": exit_code if exit_code is not None else 0,
            "timed_out": False
        }

    def run_command(self, command: str) -> Dict[str, Any]:
        """Exécute une commande dans la session persistant d'ONYX."""
        try:
            result = self._send_command(command.strip(), wait_for_prompt=True)
            if result["timed_out"]:
                return {
                    "success": False,
                    "output": result["output"],
                    "error": "Commande interrompue par timeout (30s).",
                    "exit_code": -1
                }
            
            success = (result["exit_code"] == 0)
            return {
                "success": success,
                "output": result["output"] if result["output"] else "(Exécuté sans retour)",
                "error": "" if success else f"Code de sortie : {result['exit_code']}",
                "exit_code": result["exit_code"]
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": -1
            }

    def change_directory(self, path: str):
        clean_path = path.strip("'\"")
        if self.shell_type == "powershell":
            self.run_command(f"Set-Location -Path '{clean_path}'")
        elif self.shell_type == "cmd":
            self.run_command(f"cd /d \"{clean_path}\"")
        else:
            self.run_command(f"cd '{clean_path}'")

    def _kill_shell(self):
        self._stop_reader = True
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception:
                if self.process:
                    self.process.kill()
            self.process = None

    def close(self):
        self._kill_shell()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class ShellAgent:
    """Wrapper réutilisable pour intégration dans synapse.py."""

    def __init__(self, shell_type: str = "auto"):
        self.session = ShellSession(shell_type=shell_type)

    def run_command(self, command: str) -> Dict[str, Any]:
        return self.session.run_command(command)

    def close(self):
        self.session.close()