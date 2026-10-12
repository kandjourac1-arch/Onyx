import os
import smtplib
import imaplib
import email
from email.message import EmailMessage
from email.header import decode_header
from typing import Dict, Any, List

# Configuration des identifiants (récupérées depuis les variables d'environnement)
DEFAULT_EMAIL = os.getenv("SENDER_EMAIL", "")
DEFAULT_PASSWORD = os.getenv("SENDER_PASSWORD", "")

# Configuration des serveurs
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993


def send_email(recipient: str, subject: str, body: str, 
               smtp_server: str = None, smtp_port: int = None,
               sender_email: str = None, sender_password: str = None) -> Dict[str, Any]:
    """
    Envoie un email via SMTP SSL.
    """
    smtp_server = smtp_server or os.getenv("SMTP_SERVER", SMTP_SERVER)
    smtp_port = smtp_port or int(os.getenv("SMTP_PORT", SMTP_PORT))
    sender_email = sender_email or os.getenv("SENDER_EMAIL", DEFAULT_EMAIL)
    sender_password = sender_password or os.getenv("SENDER_PASSWORD", DEFAULT_PASSWORD)
    
    # Nettoyage des espaces éventuels dans le mot de passe d'application
    sender_password = sender_password.replace(" ", "")

    if not sender_email or not sender_password:
        return {"success": False, "error": "Email ou mot de passe non configuré"}

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return {"success": True, "message": f"Email envoyé avec succès à {recipient}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_emails(limit: int = 5, unread_only: bool = True,
                imap_server: str = None, imap_port: int = None,
                sender_email: str = None, sender_password: str = None) -> Dict[str, Any]:
    """
    Récupère les derniers emails de la boîte de réception via IMAP.
    """
    imap_server = imap_server or os.getenv("IMAP_SERVER", IMAP_SERVER)
    imap_port = imap_port or int(os.getenv("IMAP_PORT", IMAP_PORT))
    sender_email = sender_email or os.getenv("SENDER_EMAIL", DEFAULT_EMAIL)
    sender_password = sender_password or os.getenv("SENDER_PASSWORD", DEFAULT_PASSWORD)

    # Nettoyage des espaces dans le mot de passe d'application
    sender_password = sender_password.replace(" ", "")

    if not sender_email or not sender_password:
        return {"success": False, "error": "Email ou mot de passe non configuré"}

    try:
        # Connexion IMAP SSL
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(sender_email, sender_password)
        mail.select("INBOX")

        # Critère de recherche
        search_criterion = "UNSEEN" if unread_only else "ALL"
        status, messages = mail.search(None, search_criterion)

        if status != "OK":
            mail.logout()
            return {"success": False, "error": "Erreur lors de la recherche dans la boîte de réception"}

        mail_ids = messages[0].split()
        if not mail_ids:
            mail.logout()
            return {"success": True, "count": 0, "emails": [], "message": "Aucun email trouvé"}

        # Récupération des N derniers emails
        latest_email_ids = mail_ids[-limit:]
        emails_list: List[Dict[str, str]] = []

        for e_id in reversed(latest_email_ids):
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # Décodage du sujet
                    subject_header = msg.get("Subject", "")
                    subject = ""
                    if subject_header:
                        decoded_chunks = decode_header(subject_header)
                        for chunk, encoding in decoded_chunks:
                            if isinstance(chunk, bytes):
                                subject += chunk.decode(encoding if encoding else "utf-8", errors="replace")
                            else:
                                subject += chunk

                    # Décodage de l'expéditeur
                    from_ = msg.get("From", "Inconnu")

                    # Extraction du corps de l'email
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body = payload.decode("utf-8", errors="replace")
                                break
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")

                    emails_list.append({
                        "id": e_id.decode(),
                        "from": from_,
                        "subject": subject,
                        "snippet": body[:200].strip() if body else ""
                    })

        mail.logout()
        return {"success": True, "count": len(emails_list), "emails": emails_list}

    except Exception as e:
        return {"success": False, "error": str(e)}