import customtkinter as ctk
import threading
from datetime import datetime

# Configuration du thème global — Design System Onyx V2
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

COLORS = {
    "bg_primary": "#08080A",
    "bg_secondary": "#0D0D0F",
    "bg_tertiary": "#141416",
    "bg_chat": "#08080A",
    "border": "rgba(255,255,255,0.08)",
    "border_hover": "rgba(255,255,255,0.15)",
    "text_primary": "#F5F5F7",
    "text_secondary": "#86868B",
    "text_tertiary": "#636366",
    "accent": "#007AFF",
    "accent_hover": "#0055B3",
    "accent_subtle": "rgba(0,122,255,0.12)",
    "success": "#30D158",
    "warning": "#FF9F0A",
    "error": "#FF3B30",
    "user_bubble": "#007AFF",
    "ai_bubble": "#141416",
    "glass": "rgba(255,255,255,0.06)",
    "glass_hover": "rgba(255,255,255,0.10)",
}

class OnyxAppleUI(ctk.CTk):
    def __init__(self, synapse_engine=None):
        super().__init__()

        self.synapse = synapse_engine
        self.title("ONYX — Core AI")
        self.geometry("980x720")
        self.configure(fg_color=COLORS["bg_primary"])

        self._create_sidebar()
        self._create_main_chat()

    def _create_sidebar(self):
        """Barre latérale minimaliste et translucide."""
        self.sidebar = ctk.CTkFrame(
            self,
            width=240,
            corner_radius=0,
            fg_color=COLORS["bg_secondary"],
            border_width=0
        )
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)

        # Header Logo & Titre
        self.logo_label = ctk.CTkLabel(
            self.sidebar,
            text="ONYX",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.logo_label.pack(anchor="w", padx=20, pady=(24, 2))

        self.subtitle_label = ctk.CTkLabel(
            self.sidebar,
            text="Neural System v2.5",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLORS["text_tertiary"]
        )
        self.subtitle_label.pack(anchor="w", padx=20, pady=(0, 18))

        # Statut du système (Pill status)
        self.status_pill = ctk.CTkFrame(
            self.sidebar,
            corner_radius=12,
            fg_color=COLORS["bg_tertiary"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.status_pill.pack(fill="x", padx=14, pady=8)

        self.status_dot = ctk.CTkLabel(
            self.status_pill,
            text="●",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["success"]
        )
        self.status_dot.pack(side="left", padx=(12, 6), pady=8)

        self.status_text = ctk.CTkLabel(
            self.status_pill,
            text="Système Prêt",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_secondary"]
        )
        self.status_text.pack(side="left", pady=8)

        # Actions rapides
        self.btn_clear = ctk.CTkButton(
            self.sidebar,
            text="Effacer la session",
            fg_color="transparent",
            border_color=COLORS["border"],
            border_width=1,
            hover_color=COLORS["glass_hover"],
            text_color=COLORS["text_secondary"],
            corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.clear_chat
        )
        self.btn_clear.pack(side="bottom", fill="x", padx=14, pady=16)

    def _create_main_chat(self):
        """Zone principale de discussion et barre de saisie flottante."""
        self.main_container = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        self.main_container.pack(side="right", fill="both", expand=True, padx=16, pady=16)

        # Zone d'affichage des messages (Scrollable)
        self.chat_history = ctk.CTkScrollableFrame(
            self.main_container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_hover"]
        )
        self.chat_history.pack(fill="both", expand=True, padx=0, pady=(0, 12))

        # Barre de saisie flottante (Pill bar style)
        self.input_container = ctk.CTkFrame(
            self.main_container,
            corner_radius=24,
            fg_color=COLORS["bg_tertiary"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.input_container.pack(fill="x", side="bottom", ipady=4)

        self.entry = ctk.CTkEntry(
            self.input_container,
            placeholder_text="Demandez quelque chose à ONYX...",
            border_width=0,
            fg_color="transparent",
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            placeholder_text_color=COLORS["text_tertiary"]
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(20, 10), pady=8)
        self.entry.bind("<Return>", lambda event: self.send_message())

        self.send_btn = ctk.CTkButton(
            self.input_container,
            text="↑",
            width=36,
            height=36,
            corner_radius=18,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            command=self.send_message
        )
        self.send_btn.pack(side="right", padx=(0, 8), pady=4)

    def add_message(self, sender: str, text: str):
        """Ajoute une bulle de message façon Apple iMessage/macOS."""
        is_user = sender.lower() == "user"

        bubble_frame = ctk.CTkFrame(
            self.chat_history,
            corner_radius=16,
            fg_color=COLORS["user_bubble"] if is_user else COLORS["ai_bubble"],
            border_width=0 if is_user else 1,
            border_color=COLORS["border"]
        )

        side_align = "e" if is_user else "w"
        bubble_frame.pack(anchor=side_align, pady=6, padx=10, fill="none")

        msg_label = ctk.CTkLabel(
            bubble_frame,
            text=text,
            justify="left",
            wraplength=500,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_primary"] if is_user else COLORS["text_primary"]
        )
        msg_label.pack(padx=16, pady=10)

    def send_message(self):
        user_input = self.entry.get().strip()
        if not user_input:
            return

        self.entry.delete(0, "end")
        self.add_message("User", user_input)
        self.update_status("Réflexion en cours...", COLORS["warning"])

        threading.Thread(target=self._process_ai_response, args=(user_input,), daemon=True).start()

    def _process_ai_response(self, prompt: str):
        if self.synapse:
            response = self.synapse.generate_response(prompt)
        else:
            response = "Moteur Synapse non connecté. Mode démo actif."

        self.after(0, self._finish_response, response)

    def _finish_response(self, response_text: str):
        self.add_message("ONYX", response_text)
        self.update_status("Système Prêt", COLORS["success"])

    def update_status(self, text: str, color: str):
        self.status_text.configure(text=text)
        self.status_dot.configure(text_color=color)

    def clear_chat(self):
        for widget in self.chat_history.winfo_children():
            widget.destroy()

if __name__ == "__main__":
    app = OnyxAppleUI()
    app.mainloop()