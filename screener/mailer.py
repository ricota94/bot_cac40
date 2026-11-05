"""Envoi SMTP (Gmail par défaut). Les graphiques sont intégrés au corps du mail (images « cid: »)."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def send(subject: str, html_body: str, images: dict[str, bytes], attachment: Path | None = None,
         sender_name: str = "Screener CAC Small") -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = os.environ.get("EMAIL_TO") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{user}>"
    msg["To"] = to
    msg.set_content("Ton client mail n'affiche pas le HTML : ouvre la pièce jointe pour lire le rapport.")
    msg.add_alternative(html_body, subtype="html")
    html_part = msg.get_payload()[1]
    for cid, png in images.items():
        html_part.add_related(png, maintype="image", subtype="png", cid=f"<{cid}>")
    if attachment:
        msg.add_attachment(attachment.read_bytes(), maintype="text", subtype="html", filename=attachment.name)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=ctx)
            s.login(user, password)
            s.send_message(msg)
