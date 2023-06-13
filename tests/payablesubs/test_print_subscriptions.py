"""Tests for the print_subscriptions module."""
import pytest
from payablesubs.management.commands.print_subscriptions import Command
from test_models import create_user_and_group, create_subscription

pytestmark = pytest.mark.django_db  # pylint: disable=invalid-name

@pytest.fixture
def subscription(django_user_model):
    john, _ = create_user_and_group(django_user_model)
    return create_subscription(john)

@pytest.fixture
def command():
    return Command()

def test_print_subscriptions(command, subscription):
    args = {
        "cost": "ALL",
        "include_inactive": False,
        "email_to": None,
    }
    command.handle(**args)