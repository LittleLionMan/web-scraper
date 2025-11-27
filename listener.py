import hashlib
import logging
import os
import time

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

URL = "https://www.olg-hamm.nrw.de/aufgaben/geschaeftsverteilung/verwaltung/dez05-neu/01_Einstellungsverfahren/index.php"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "900"))
HASH_FILE = os.getenv("HASH_FILE", "./hashes.txt")

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_NAME = os.getenv("FROM_NAME", "OLG Watcher")
MAIL_TO = os.getenv("MAIL_TO")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        logger.debug("Telegram-Benachrichtigung übersprungen: Variablen fehlen")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram-Nachricht gesendet")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Telegram-Versand: {e}")
        return False


def send_mail(subject, body):
    if not (BREVO_API_KEY and FROM_EMAIL and MAIL_TO):
        logger.debug("Mailversand übersprungen: Brevo-Variablen fehlen")
        return False

    recipients = [{"email": email.strip()} for email in MAIL_TO.split(",")]

    payload = {
        "sender": {"name": FROM_NAME, "email": FROM_EMAIL},
        "to": recipients,
        "subject": subject,
        "textContent": body,
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY,
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        logger.info(f"Mail via Brevo gesendet: {subject}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Brevo-Mailversand: {e}")
        return False


def notify(subject, body):
    telegram_sent = send_telegram(f"<b>{subject}</b>\n\n{body}")
    mail_sent = send_mail(subject, body)

    if not telegram_sent and not mail_sent:
        logger.warning("Keine Benachrichtigung konnte versendet werden!")


def fetch_page():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    response = requests.get(URL, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text


def extract_training_section(html):
    soup = BeautifulSoup(html, "html.parser")
    header = soup.find("h5", string="Kurzfristig zu besetzende Ausbildungsplätze:")
    if not header:
        logger.debug("Ausbildungsbereich-Header nicht gefunden")
        return None

    content_parts = []
    for sibling in header.find_next_siblings():
        if sibling.name and sibling.name.startswith("h"):
            break
        content_parts.append(str(sibling))

    combined = "\n".join(content_parts).strip()
    return combined if combined else None


def get_hash(content):
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def load_hashes():
    if not os.path.exists(HASH_FILE):
        logger.info("Keine vorherige Hash-Datei gefunden - erster Durchlauf")
        return None, None
    try:
        with open(HASH_FILE, "r") as f:
            lines = f.read().splitlines()
            if len(lines) == 2:
                logger.debug("Hashes erfolgreich geladen")
                return lines[0], lines[1]
    except Exception as e:
        logger.error(f"Fehler beim Lesen der Hash-Datei: {e}")
    return None, None


def save_hashes(full_hash, section_hash):
    os.makedirs(os.path.dirname(HASH_FILE) or ".", exist_ok=True)
    with open(HASH_FILE, "w") as f:
        f.write(full_hash + "\n")
        f.write(section_hash + "\n")
    logger.debug("Hashes gespeichert")


def main():
    logger.info("🚀 OLG Hamm Watcher gestartet")
    logger.info(f"URL: {URL}")
    logger.info(f"Check-Intervall: {CHECK_INTERVAL} Sekunden")
    logger.info(f"Hash-Datei: {HASH_FILE}")

    channels = []
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        channels.append("Telegram")
    if BREVO_API_KEY and FROM_EMAIL and MAIL_TO:
        channels.append("E-Mail")

    if channels:
        logger.info(f"Benachrichtigungskanäle: {', '.join(channels)}")
    else:
        logger.warning("⚠️ Keine Benachrichtigungskanäle konfiguriert!")

    last_full_hash, last_section_hash = load_hashes()

    while True:
        try:
            logger.info("Prüfe Webseite...")
            html = fetch_page()
            full_hash = get_hash(html)
            section = extract_training_section(html)
            section_hash = get_hash(section)

            if last_full_hash is None:
                logger.info(
                    "Erster Durchlauf - Baseline gesetzt, keine Benachrichtigung versendet"
                )
            else:
                if full_hash != last_full_hash:
                    logger.warning("⚠️ Strukturänderung auf der Seite erkannt!")
                    notify(
                        "OLG Hamm – Strukturänderung erkannt",
                        "Die Gesamtstruktur der Seite hat sich verändert (möglicherweise Layout oder Position des Ausbildungsbereichs).",
                    )

                if section_hash != last_section_hash:
                    logger.info("✅ Änderung im Ausbildungsabschnitt erkannt!")
                    msg = (
                        "Der Inhalt im Ausbildungsabschnitt hat sich geändert.\n\n"
                        f"Aktueller Inhalt:\n\n{section or '[leer]'}"
                    )
                    notify("OLG Hamm – Ausbildungsplatz-Update!", msg)
                else:
                    logger.info("Keine Änderungen festgestellt")

            save_hashes(full_hash, section_hash)
            last_full_hash, last_section_hash = full_hash, section_hash

        except requests.exceptions.RequestException as e:
            logger.error(f"Fehler beim Abrufen der Webseite: {e}")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler: {e}", exc_info=True)

        logger.info(f"Warte {CHECK_INTERVAL} Sekunden bis zum nächsten Check...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
