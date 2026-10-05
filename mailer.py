"""Transactional delivery without exposing reset links or provider credentials."""
import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage


def configured():
    return bool((os.getenv('RESEND_API_KEY') and (os.getenv('RESEND_FROM_EMAIL') or os.getenv('RESEND_FROM')))
                or (os.getenv('SMTP_HOST') and (os.getenv('SMTP_FROM') or os.getenv('SMTP_USERNAME'))))


def send(to, subject, text):
    key = os.getenv('RESEND_API_KEY', '')
    sender = os.getenv('RESEND_FROM_EMAIL') or os.getenv('RESEND_FROM', '')
    if key and sender:
        req = urllib.request.Request('https://api.resend.com/emails',
            data=json.dumps({'from': sender, 'to': [to], 'subject': subject, 'text': text}).encode(),
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'MexAy-Upwork-Agent/2.1'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status < 300:
                    return True
        except Exception:
            pass
    host = os.getenv('SMTP_HOST', '')
    sender = os.getenv('SMTP_FROM') or os.getenv('SMTP_USERNAME', '')
    if not host or not sender:
        return False
    try:
        port = int(os.getenv('SMTP_PORT', '587'))
        msg = EmailMessage()
        msg['From'], msg['To'], msg['Subject'] = sender, to, subject
        msg.set_content(text)
        cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with cls(host, port, timeout=15) as smtp:
            if port != 465:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
            if os.getenv('SMTP_USERNAME'):
                smtp.login(os.environ['SMTP_USERNAME'], os.getenv('SMTP_PASSWORD', ''))
            smtp.send_message(msg)
        return True
    except Exception:
        return False
