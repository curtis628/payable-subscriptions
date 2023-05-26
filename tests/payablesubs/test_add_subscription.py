"""Tests for the add_subscriptions module."""
import unittest
from unittest import mock
from unittest.mock import Mock
from datetime import datetime
from decimal import Decimal
import venmo_api
import uuid

import pytest
from payablesubs.management.commands.add_subscription import Command
from test_models import create_due_subscription, create_user_and_group, create_venmo_user, create_cost, TEST_PLAN_GRACE_DAYS, create_subscription
from subscriptions.models import UserSubscription
from payablesubs.models import VenmoAccount
from django.contrib.auth import get_user_model

MOCK_USER_VENMO_ID = str(uuid.uuid4())
MOCK_VENMO_USERNAME = "user-venmo-username"
MOCK_VENMO_USER = venmo_api.models.user.User(MOCK_USER_VENMO_ID, MOCK_VENMO_USERNAME, None, None, None, None, None, None, None, None, None)

MOCK_PROFILE_VENMO_ID = str(uuid.uuid4())
MOCK_PROFILE_VENMO_USER = venmo_api.models.user.User(MOCK_PROFILE_VENMO_ID, "root-venmo-username", None, None, None, None, None, None, None, None, None)

pytestmark = pytest.mark.django_db  # pylint: disable=invalid-name

@pytest.fixture
def subscription(django_user_model):
    john, _ = create_user_and_group(django_user_model)
    return create_subscription(john)

@pytest.fixture
def command():
    mock_client = Mock()
    mock_client.user.get_user_by_username = Mock(return_value=MOCK_VENMO_USER)
    return Command(mock_client)

@mock.patch('payablesubs.management.commands.add_subscription.getpass')
def test_add_sub_no_venmo(mock_getpass_func, subscription, command):
    assert get_user_model().objects.count() == 1
    assert UserSubscription.objects.count() == 1

    args = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "janedoe@email.com",
        "plan": "Test Plan",
        "start_date": datetime.fromisoformat("2022-01-15"),
        "cost": None,
        "venmo_username": None,
    }
    mock_getpass_func.return_value = 'mocked-password'
    command.handle(**args)

    assert get_user_model().objects.count() == 2
    assert UserSubscription.objects.count() == 2
    assert VenmoAccount.objects.count() == 0

@mock.patch('payablesubs.management.commands.add_subscription.getpass')
def test_add_sub_with_venmo(mock_getpass_func, subscription, command):
    args = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "janedoe@email.com",
        "plan": "Test Plan",
        "start_date": datetime.fromisoformat("2022-01-15"),
        "cost": None,
        "venmo_username": MOCK_VENMO_USERNAME,
    }
    mock_getpass_func.return_value = 'mocked-password'
    command.handle(**args)

    assert get_user_model().objects.count() == 2
    assert UserSubscription.objects.count() == 2
    assert VenmoAccount.objects.count() == 1
    assert VenmoAccount.objects.first().venmo_id == MOCK_USER_VENMO_ID
    assert VenmoAccount.objects.first().venmo_username == MOCK_VENMO_USERNAME

@mock.patch('payablesubs.management.commands.add_subscription.getpass')
def test_add_sub_wrong_cost(mock_getpass_func, subscription, command):
    args = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "janedoe@email.com",
        "plan": "Test Plan",
        "start_date": datetime.fromisoformat("2022-01-15"),
        "cost": Decimal(2), # No PlanCost with $2 amount
        "venmo_username": None,
    }
    mock_getpass_func.return_value = 'mocked-password'

    with pytest.raises(RuntimeError) as excinfo:
        command.handle(**args)

    assert "No PlanCost exists for 'Test Plan' with cost=2." == str(excinfo.value)
@mock.patch('payablesubs.management.commands.add_subscription.getpass')
def test_add_sub_right_cost(mock_getpass_func, subscription, command):
    args = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "janedoe@email.com",
        "plan": "Test Plan",
        "start_date": datetime.fromisoformat("2022-01-15"),
        "cost": Decimal(1), # Matches
        "venmo_username": None,
    }
    mock_getpass_func.return_value = 'mocked-password'
    command.handle(**args)

    assert get_user_model().objects.count() == 2
    assert UserSubscription.objects.count() == 2
