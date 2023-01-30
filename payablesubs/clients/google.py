"""Provides reusable access to `google-api-python-client` client"""
import logging
from pathlib import Path

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/contacts"]

CREDENTIALS_FOLDER = Path(".credentials")
CREDENTIALS_FILE = CREDENTIALS_FOLDER / "credentials.json"
TOKEN_FILE = CREDENTIALS_FOLDER / "token.json"
GOOGLE_CONTACT_GROUP_ID = settings.PAYABLESUBS_GOOGLE_CONTACT_LABEL

_INSTANCE = None


def _is_enabled():
    enabled = GOOGLE_CONTACT_GROUP_ID is not None
    if not enabled:
        logger.warning("Google integration not enabled...")
    return enabled


def get_client():
    """Returns the initialized `google-api-python-client` instance.

    Credentials logic taken from: https://developers.google.com/people/quickstart/python

    Returns:
      A Resource object with methods for interacting with the service.

      ```
      service = google.get_client()
      response = service.people().searchContacts(query="email", readMask="emailAddresses,memberships").execute()
      ```
    """
    if not _is_enabled():
        return

    global _INSTANCE
    if not _INSTANCE:
        logger.debug("Initializing google-api-python-client...")
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is created
        # automatically when the authorization flow completes for the first time.
        if TOKEN_FILE.exists():
            logger.debug(f"   ... initializing from existing {TOKEN_FILE}")
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.debug("   ... refreshing expired token.json")
                creds.refresh(Request())
            else:
                logger.debug(f"   ... fresh initialization using {CREDENTIALS_FILE} + {SCOPES=}")
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(TOKEN_FILE, "w") as token:
                logger.debug(f"   ... writing {TOKEN_FILE} to file")
                token.write(creds.to_json())

        _INSTANCE = build("people", "v1", credentials=creds)
    return _INSTANCE


def remove_contact_label(user, client=None):
    if not _is_enabled():
        return
    client = client if client else get_client()
    search_result = client.people().searchContacts(query=user.email, readMask="emailAddresses").execute()
    if not search_result or len(search_result["results"]) != 1:
        logger.warning(f"Found unexpected {search_result=}")
        raise Exception(f"{user.email} found unexpected results from Google")

    person_resource_name = search_result["results"][0]["person"]["resourceName"]
    body = {"resourceNamesToRemove": [person_resource_name]}
    client.contactGroups().members().modify(
        resourceName=f"contactGroups/{GOOGLE_CONTACT_GROUP_ID}", body=body
    ).execute()
    logger.debug(f"Removed {user} [{person_resource_name}] from contact group {GOOGLE_CONTACT_GROUP_ID}")


def add_contact_label(user, client=None):
    if not _is_enabled():
        return
    client = client if client else get_client()

    search_result = client.people().searchContacts(query=user.email, readMask="emailAddresses").execute()
    if not search_result:
        body = {
            "emailAddresses": [{"value": user.email}],
            "names": [{"givenName": user.first_name, "familyName": user.last_name}],
        }
        logger.info(f"Creating new Google contact for {user}")
        person = client.people().createContact(body=body).execute()
    elif len(search_result["results"]) > 1:
        raise Exception(f"{user.email} Found results from {len(search_result['results'])} results from Google")
    else:
        person = search_result["results"][0]["person"]

    person_resource_name = person["resourceName"]
    body = {"resourceNamesToAdd": [person_resource_name]}
    client.contactGroups().members().modify(
        resourceName=f"contactGroups/{GOOGLE_CONTACT_GROUP_ID}", body=body
    ).execute()
    logger.debug(f"Added {user} [{person_resource_name}] to contact group {GOOGLE_CONTACT_GROUP_ID}")
