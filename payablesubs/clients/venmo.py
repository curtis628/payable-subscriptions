"""Provides reusable access to `venmo-api` client"""
import logging
from getpass import getpass
from pathlib import Path

from venmo_api import Client

CREDENTIALS_FOLDER = Path(".credentials")
TOKEN_FILE = CREDENTIALS_FOLDER / "venmo.token"

logger = logging.getLogger(__name__)
_INSTANCE = None


def get_client():
    global _INSTANCE
    if not _INSTANCE:
        logger.debug("Initializing Venmo client...")
        access_token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else getpass("Venmo Access Token: ")
        _INSTANCE = Client(access_token)
    return _INSTANCE
