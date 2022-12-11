"""Tests for the _venmo_manager module."""

import pytest
from decimal import Decimal

from unittest.mock import Mock
from django.contrib.auth.models import Group
from django.utils import timezone as django_timezone
from datetime import datetime, timezone
import uuid
import random
from datetime import timedelta


from subscriptions import models
from venmosubs.models import Bill, VenmoAccount, VenmoTransaction
from venmosubs.management.commands.venmo_manager import VenmoManager

import venmo_api.models.user
from venmo_api.models.transaction import Transaction
from test_models import create_due_subscription, create_user_and_group, create_venmo_user, TEST_PLAN_GRACE_DAYS

TEST_USERNAME = "test-subscriber"
TEST_GROUP = "test-group"
TEST_PLAN = "Test Plan"

MOCK_PROFILE_VENMO_ID = str(uuid.uuid4())
MOCK_PROFILE_VENMO_USER = venmo_api.models.user.User(MOCK_PROFILE_VENMO_ID, "root-venmo-username", None, None, None, None, None, None, None, None, None)


pytestmark = pytest.mark.django_db  # pylint: disable=invalid-name

@pytest.fixture
def manager():
    mock_client = Mock()

    mock_client.my_profile = Mock(return_value=MOCK_PROFILE_VENMO_USER)
    mock_client.user = Mock()

    mock_client.payment = Mock()
    mock_client.payment.request_money = Mock(return_value=True)

    mock_client.user.get_user_transactions = Mock(return_value=[])

    return VenmoManager(mock_client)

@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username=TEST_USERNAME, first_name="John", last_name="Doe", email="jdoe@email.com", password="uncrackable:)")


@pytest.fixture
def venmo_user(django_user_model, user):
    return create_venmo_user(django_user_model, user)


@pytest.fixture
def group(user):
    group = Group.objects.create(name=TEST_GROUP)
    group.user_set.add(user)
    return group


@pytest.fixture
def due_subscription(user, group):
    """Creates a subscription for `user` + `group` that is currently due."""
    return create_due_subscription(user, group)

@pytest.fixture
def bill(user, due_subscription):
    plan_cost = due_subscription.subscription
    return Bill.objects.create(user=user, subscription=plan_cost, amount=plan_cost.cost, date_transaction=due_subscription.date_billing_next)

def test_manager_process_expired(manager, user, due_subscription, venmo_user):
    """Basic test for handling expired subscription. Ensures bill is sent and persisted."""
    initial_date_billing_next = due_subscription.date_billing_next
    manager.process_subscriptions()

    # Confirm that venmo request_money was called as expected
    manager.client.payment.request_money.assert_called_once()
    amount, note, venmo_id = manager.client.payment.request_money.call_args.args

    assert amount == float(due_subscription.subscription.cost)
    assert user.first_name in note
    assert venmo_id == str(venmo_user.venmo_id)

    # Ensure Subscription and Bill data looks good.
    subscription = models.UserSubscription.objects.get(id=due_subscription.id)
    assert subscription.active is True
    assert subscription.cancelled is False
    assert subscription.date_billing_next == initial_date_billing_next # subscription still due since no payments

    assert Bill.objects.count() == 1
    bill = Bill.objects.first()
    assert bill.user == user
    assert bill.amount == subscription.subscription.cost
    assert bill.date_transaction == subscription.date_billing_next

    assert VenmoTransaction.objects.count() == 0


def test_manager_process_expired_no_duplicate_bills(manager, due_subscription, venmo_user):
    """Duplicate bills and venmo requests aren't created."""
    manager.process_subscriptions()
    manager.process_subscriptions()

    manager.client.payment.request_money.assert_called_once()
    assert Bill.objects.count() == 1


def _create_txn(amount, actor, target, date_completed=None, payment_type="pay", note="test payment"):
    if date_completed:
        date_completed = int(date_completed.timestamp())
    return Transaction(random.randint(1,10000), None, date_completed, date_completed, date_completed,
                       payment_type, float(amount), None, None, note, None, actor, target, None)

def _venmo_account_to_api_model(venmo_account):
    """Translates a `VenmoAccount` object to a `venmo_api.models.user.User` object."""
    return venmo_api.models.user.User(venmo_account.venmo_id, venmo_account.venmo_username, None, None, None, None, None, None, None, None, None)

def _process_and_verify(manager, bill, mock_txn=None, expected_transactions=0):
    sub = bill.subscription.subscriptions.first()
    initial_billing_next = sub.date_billing_next
    if mock_txn:
        manager.client.user.get_user_transactions = Mock(return_value=[mock_txn])

    assert VenmoTransaction.objects.count() == 0
    manager.process_subscriptions()
    assert VenmoTransaction.objects.count() == expected_transactions

    # If a transaction was matched, the sub's next billing date should be moved out
    latest_sub = models.UserSubscription.objects.get(id=sub.id)
    if expected_transactions:
        txn = VenmoTransaction.objects.first()
        assert txn.amount == mock_txn.amount
        assert txn.user == bill.user
        assert txn.subscription == bill.subscription
        assert txn.date_transaction == datetime.fromtimestamp(mock_txn.date_completed, tz=timezone.utc)
        assert txn.amount == bill.amount
        assert txn.venmo_id == mock_txn.id

        assert latest_sub.date_billing_next > initial_billing_next
    else:
        assert latest_sub.date_billing_next == initial_billing_next


def test_manager_process_subscriber_pay_match(manager, bill, venmo_user):
    """Ensures that when subscriber pays us for the expected cost, it gets matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount, actor=venmo_subscriber, target=MOCK_PROFILE_VENMO_USER, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 1)

def test_manager_process_subscriber_charge_match(manager, bill, venmo_user):
    """Ensures that when subscriber is charged for the expected cost, it gets matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount, payment_type="charge", actor=MOCK_PROFILE_VENMO_USER, target=venmo_subscriber, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 1)

def test_manager_process_subscriber_pay_wrong_amount_nomatch(manager, bill, venmo_user):
    """Ensures that when subscriber pays us for an unexpected cost, it doesn't get matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount + 1, actor=venmo_subscriber, target=MOCK_PROFILE_VENMO_USER, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 0)

def test_manager_process_subscriber_charge_wrong_amount_nomatch(manager, bill, venmo_user):
    """Ensures that when subscriber is charged for an unexpected cost, it doesn't get matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount - Decimal(.5), payment_type="charge", actor=MOCK_PROFILE_VENMO_USER, target=venmo_subscriber, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 0)

def test_manager_process_root_pay_nomatch(manager, bill, venmo_user):
    """Ensures that when root pays subscriber for plan cost, it doesn't get matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount, actor=MOCK_PROFILE_VENMO_USER, target=venmo_subscriber, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 0)

def test_manager_process_multiple_subscriptions_processed(manager, django_user_model):
    john_user, group = create_user_and_group(django_user_model, "John", "Doe")
    john_venmo_acct = create_venmo_user(django_user_model, john_user)
    jane_user, group = create_user_and_group(django_user_model, "Jane", "Doe")
    jane_venmo_acct = create_venmo_user(django_user_model, jane_user)

    john_sub = create_due_subscription(john_user, group)
    initial_john_billing_next = john_sub.date_billing_next
    jane_sub = create_due_subscription(jane_user, group)
    initial_jane_billing_next = jane_sub.date_billing_next
    assert initial_john_billing_next == initial_jane_billing_next

    john_venmo_api = _venmo_account_to_api_model(john_venmo_acct)
    jane_venmo_api = _venmo_account_to_api_model(jane_venmo_acct)

    # John pays (via a completed 'charge') his subscription
    john_charge_match = _create_txn(john_sub.subscription.cost, payment_type="charge", actor=MOCK_PROFILE_VENMO_USER, target=john_venmo_api, date_completed=john_sub.date_billing_next)
    # *We* paid Jane, which shouldn't match (and so subscription isn't paid yet)
    jane_pay_nomatch = _create_txn(jane_sub.subscription.cost, payment_type="pay", actor=MOCK_PROFILE_VENMO_USER, target=jane_venmo_api, date_completed=jane_sub.date_billing_next)
    manager.client.user.get_user_transactions = Mock(return_value=[john_charge_match, jane_pay_nomatch])

    assert Bill.objects.count() == 0
    assert models.SubscriptionTransaction.objects.count() == 0
    assert VenmoTransaction.objects.count() == 0

    manager.process_subscriptions()

    assert Bill.objects.count() == 2
    assert manager.client.payment.request_money.call_count == 2 # sent out 2 Bills
    assert VenmoTransaction.objects.count() == 1 # only matched/saved 1 transaction

    # John paid... so his subscription was updated
    latest_john_sub = models.UserSubscription.objects.get(id=john_sub.id)
    assert initial_john_billing_next < latest_john_sub.date_billing_next

    # Jane still hasn't paid... so her subscription is the same
    latest_jane_sub = models.UserSubscription.objects.get(id=jane_sub.id)
    assert initial_jane_billing_next == latest_jane_sub.date_billing_next

    # We only called out to Venmo to get transactions once (and cached result)
    manager.client.user.get_user_transactions.assert_called_once()

def test_manager_process_share_venmo_accounts(manager, django_user_model):
    """In this test, John and Jane share the same venmo username! Ensure payments processed as expected."""
    john_user, group = create_user_and_group(django_user_model, "John", "Doe")
    shared_venmo_username = "shared-venmo-user"
    john_venmo_acct = create_venmo_user(django_user_model, john_user, venmo_username=shared_venmo_username)
    jane_user, group = create_user_and_group(django_user_model, "Jane", "Doe")
    create_venmo_user(django_user_model, jane_user, venmo_username=shared_venmo_username, venmo_id=john_venmo_acct.venmo_id)

    john_sub = create_due_subscription(john_user, group)
    jane_sub = create_due_subscription(jane_user, group)
    shared_venmo_api = _venmo_account_to_api_model(john_venmo_acct)

    john_charge_match = _create_txn(john_sub.subscription.cost, payment_type="charge", actor=MOCK_PROFILE_VENMO_USER, target=shared_venmo_api, date_completed=john_sub.date_billing_next, note="john-payment")
    jane_charge_match = _create_txn(jane_sub.subscription.cost, payment_type="charge", actor=MOCK_PROFILE_VENMO_USER, target=shared_venmo_api, date_completed=jane_sub.date_billing_next, note="jane-payment")
    manager.client.user.get_user_transactions = Mock(return_value=[john_charge_match, jane_charge_match])

    manager.process_subscriptions()
    assert Bill.objects.count() == 2
    assert VenmoTransaction.objects.count() == 2

def test_manager_process_cancels_after_grace_period(manager, due_subscription, venmo_user):
    initial_date_billing_next = due_subscription.date_billing_next
    assert due_subscription.active is True
    assert due_subscription.cancelled is False
    assert due_subscription.date_billing_end is None

    # After processing... date_billing_end set according to plan's grace period
    manager.process_subscriptions()
    latest_sub = models.UserSubscription.objects.get(id=due_subscription.id)
    assert latest_sub.active is True
    assert latest_sub.cancelled is False
    assert latest_sub.date_billing_end == initial_date_billing_next + timedelta(days=TEST_PLAN_GRACE_DAYS)

    # After grace period ends (and processed again), sub is cancelled
    manager.process_subscriptions()
    latest_sub = models.UserSubscription.objects.get(id=due_subscription.id)
    assert latest_sub.active is False
    assert latest_sub.cancelled is True

    assert Bill.objects.count() == 1
    assert VenmoTransaction.objects.count() == 0
    manager.client.payment.request_money.assert_called_once()

def test_manager_process_resets_after_payment(manager, due_subscription, venmo_user):
    initial_date_billing_next = due_subscription.date_billing_next
    manager.process_subscriptions()
    latest_sub = models.UserSubscription.objects.get(id=due_subscription.id)
    assert latest_sub.active is True
    assert latest_sub.cancelled is False
    assert latest_sub.date_billing_next == initial_date_billing_next
    assert latest_sub.date_billing_end == initial_date_billing_next + timedelta(days=TEST_PLAN_GRACE_DAYS)

    # bump out billing end to test payments during grace period process
    latest_sub.date_billing_end = django_timezone.now() + timedelta(days=2)
    latest_sub.save()

    bill = Bill.objects.first()
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount, actor=venmo_subscriber, target=MOCK_PROFILE_VENMO_USER, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 1)

    latest_sub = models.UserSubscription.objects.get(id=due_subscription.id)
    assert latest_sub.active is True
    assert latest_sub.cancelled is False
    assert latest_sub.date_billing_next > initial_date_billing_next
    assert latest_sub.date_billing_end is None
