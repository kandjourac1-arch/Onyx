import os
import smtplib
import imaplib
import email
import ssl
from email.message import EmailMessage
from email.header import decode_header
from typing import Dict, Any, List

# Configuration par défaut pour Proton Mail Bridge (localhost)
DEFAULT_EMAIL = os.getenv("PROTON_EMAIL", "votre_adresse@proton.me")
DEFAULT_PASSWORD = os.getenv("PROTON_PASSWORD", "")

SMTP_SERVER = os.getenv("PROTON_SMTP_SERVER", "127.0.0.1")
SMTP_PORT = int(os.getenv("PROTON_SMTP_PORT", 1025))

IMAP_SERVER = os.getenv("PROTON_IMAP_SERVER", "127.0.0.1")
IMAP_PORT = int(os.getenv("PROTON_IMAP_PORT", 1143))


def send_email_proton(recipient: str, subject: str, body: str) -> Dict[str, Any]:
    """
    Envoie un email via Proton Mail Bridge (SMTP local).
    """
    if not DEFAULT_EMAIL or not DEFAULT_PASSWORD:
        return {"success": False, "error": "Identifiants Proton non configurés"}

    msg = EmailMessage()
    msg["From"] = DEFAULT_EMAIL
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        # Désactivation de la vérification stricte du certificat SSL pour le localhost
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls(context=context)
            server.login(DEFAULT_EMAIL, DEFAULT_PASSWORD)
            server.send_message(msg)
            
        return {"success": True, "message": f"Email envoyé via Proton à {recipient}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_emails_proton(limit: int = 5, unread_only: bool = True) -> Dict[str, Any]:
    """
    Lit les emails via Proton Mail Bridge (IMAP local).
    """
    if not DEFAULT_EMAIL or not DEFAULT_PASSWORD:
        return {"success": False, "error": "Identifiants Proton non configurés"}

    try:
        # Context SSL assoupli pour le certificat auto-signé de Proton Bridge
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # IMAP avec STARTTLS sur le port local Bridge
        mail = imaplib.IMAP4(IMAP_SERVER, IMAP_PORT)
        mail.starttls(ssl_context=context)
        mail.login(DEFAULT_EMAIL, DEFAULT_PASSWORD)
        mail.select("INBOX")

        search_criterion = "UNSEEN" if unread_only else "ALL"
        status, messages = mail.search(None, search_criterion)

        if status != "OK":
            mail.logout()
            return {"success": False, "error": "Erreur lors de la recherche dans la boîte Proton"}

        mail_ids = messages[0].split()
        if not mail_ids:
            mail.logout()
            return {"success": True, "count": 0, "emails": [], "message": "Aucun email trouvé"}

        latest_email_ids = mail_ids[-limit:]
        emails_list: List[Dict[str, str]] = []

        for e_id in reversed(latest_email_ids):
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    subject_header = msg.get("Subject", "")
                    subject = ""
                    if subject_header:
                        decoded_chunks = decode_header(subject_header)
                        for chunk, encoding in decoded_chunks:
                            if isinstance(chunk, bytes):
                                subject += chunk.decode(encoding if encoding else "utf-8", errors="replace")
                            else:
                                subject += chunk

                    from_ = msg.get("From", "Inconnu")
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