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
from payablesubs.models import Bill, Payment
from payablesubs.management.commands._payable_manager import PayableManager

import payablesubs.clients.google as google
import venmo_api.models.user
from venmo_api.models.transaction import Transaction
from test_models import create_due_subscription, create_user_and_group, create_venmo_user, create_cost, TEST_PLAN_GRACE_DAYS, create_subscription
from django.conf import settings

TEST_USERNAME = "test-subscriber"
TEST_GROUP = "test-group"
TEST_PLAN = "Test Plan"

MOCK_PROFILE_VENMO_ID = str(uuid.uuid4())
MOCK_PROFILE_VENMO_USER = venmo_api.models.user.User(MOCK_PROFILE_VENMO_ID, "root-venmo-username", None, None, None, None, None, None, None, None, None)


pytestmark = pytest.mark.django_db  # pylint: disable=invalid-name

@pytest.fixture
def manager():
    mock_venmo = Mock()
    mock_venmo.my_profile = Mock(return_value=MOCK_PROFILE_VENMO_USER)
    mock_venmo.user = Mock()

    mock_venmo.payment = Mock()
    mock_venmo.payment.request_money = Mock(return_value=True)
    mock_venmo.user.get_user_transactions = Mock(return_value=[])

    mock_google = Mock()
    return PayableManager(venmo_client=mock_venmo, google_client=mock_google)

@pytest.fixture
def user(django_user_model):
    return create_user_and_group(django_user_model)[0]


@pytest.fixture
def venmo_user(django_user_model, user):
    return create_venmo_user(django_user_model, user)


@pytest.fixture
def group(user):
    group, _ = Group.objects.get_or_create(name=TEST_GROUP)
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

def test_due_subscription(manager, user, due_subscription, venmo_user):
    """Basic test for handling expired subscription. Ensures bill is sent and persisted."""
    initial_date_billing_next = due_subscription.date_billing_next
    manager.process_subscriptions()

    # Confirm that venmo request_money was called as expected
    manager.venmo_client.payment.request_money.assert_called_once()
    amount, note, venmo_id = manager.venmo_client.payment.request_money.call_args.args

    assert amount == float(due_subscription.subscription.cost)
    assert note == "John's Test Plan subscription for Feb 2018"
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

    assert Payment.objects.count() == 0

def test_due_subscription_billing_disabled(manager, due_subscription, venmo_user):
    settings.PAYABLESUBS_BILLING_ENABLED = False
    try:
        manager.process_subscriptions()
    finally:
        settings.PAYABLESUBS_BILLING_ENABLED = True

    manager.venmo_client.payment.request_money.assert_not_called()

def test_due_subscription_dry_run_enabled(manager, due_subscription, venmo_user):
    initial_date_billing_next = due_subscription.date_billing_next
    initial_date_billing_end = due_subscription.date_billing_end
    assert initial_date_billing_next < django_timezone.now()
    assert initial_date_billing_end is None
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)

    amount = due_subscription.subscription.cost
    mock_txn = _create_txn(amount, actor=venmo_subscriber, target=MOCK_PROFILE_VENMO_USER, date_completed=initial_date_billing_next)
    manager.venmo_client.user.get_user_transactions = Mock(return_value=[mock_txn])

    settings.PAYABLESUBS_DRY_RUN = True
    try:
        manager.process_subscriptions()
    finally:
        settings.PAYABLESUBS_DRY_RUN = False

    # No payment request sent - and no Payment's persisted
    manager.venmo_client.payment.request_money.assert_not_called()
    assert Bill.objects.count() == 0
    assert Payment.objects.count() == 0

    # subscription hasn't changed
    subscription = models.UserSubscription.objects.get(id=due_subscription.id)
    assert subscription.active is True
    assert subscription.cancelled is False
    assert subscription.date_billing_next == initial_date_billing_next
    assert subscription.date_billing_end == initial_date_billing_end

def test_bills_with_different_plan_cost(django_user_model, manager):
    john, group = create_user_and_group(django_user_model, first_name="John")
    create_venmo_user(django_user_model, john)
    due_sub = create_due_subscription(john, group=group)
    plan = due_sub.subscription.plan

    jane, _ = create_user_and_group(django_user_model, first_name="Jane")
    create_venmo_user(django_user_model, jane)
    jane_cost = create_cost(group, plan, amount=Decimal(10))
    create_due_subscription(jane, group, jane_cost)

    manager.process_subscriptions()
    request_money_mock = manager.venmo_client.payment.request_money
    assert request_money_mock.call_count == 2
    call_1, call_2 = request_money_mock.call_args_list[0], request_money_mock.call_args_list[1]

    amount, note, _ = call_1.args
    assert amount == float(1.0)
    assert note == "John's Test Plan subscription for Feb 2018"

    amount, note, _ = call_2.args
    assert amount == float(10.0)
    assert note == "Jane's Test Plan subscription for Feb 2018"

def test_due_end_of_month(manager, due_subscription, venmo_user):
    # change due_subscription's next billing month to start at the end of last month
    due_subscription.date_billing_next -= timedelta(days=5)
    due_subscription.save()
    manager.process_subscriptions()

    # Confirm that venmo request_money was called as expected
    manager.venmo_client.payment.request_money.assert_called_once()
    _, note, _ = manager.venmo_client.payment.request_money.call_args.args
    assert note == "John's Test Plan subscription for Feb 2018"

def test_generate_note(django_user_model, manager):
    john, group = create_user_and_group(django_user_model, first_name="John")
    jan1_2018 = datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)

    every_6_months = create_cost(group, amount=Decimal(5), recurrence_period=6, recurrence_unit=models.MONTH)
    plan = every_6_months.plan
    every_year = create_cost(group, plan=plan, amount=Decimal(10), recurrence_period=1, recurrence_unit=models.YEAR)

    john_sub = create_subscription(john, cost=every_6_months, group=group, date_start=jan1_2018, date_next=jan1_2018)
    assert manager._generate_note(john_sub) == "John's Test Plan subscription for Jan - Jun 2018"

    feb28_2022 = datetime(2022, 2, 28, 1, 1, 1, tzinfo=timezone.utc)
    jane, _ = create_user_and_group(django_user_model, first_name="Jane")
    jane_sub = create_subscription(jane, cost=every_year, group=group, date_start=feb28_2022, date_next=feb28_2022)
    assert manager._generate_note(jane_sub) == "Jane's Test Plan subscription for Mar - Feb 2023"


def test_due_no_duplicate_bills(manager, due_subscription, venmo_user):
    """Duplicate bills and venmo requests aren't created."""
    manager.process_subscriptions()
    manager.process_subscriptions()

    manager.venmo_client.payment.request_money.assert_called_once()
    assert Bill.objects.count() == 1

def test_due_bills_sent_for_each_user(django_user_model, manager, user, group, due_subscription, venmo_user):
    plan_cost = due_subscription.subscription

    # Add another subscription to the same PlanCost
    jane, _ =  create_user_and_group(django_user_model, first_name="Jane")
    _ = create_due_subscription(jane, group, plan_cost)
    assert models.PlanCost.objects.count() == 1
    plan_cost = models.PlanCost.objects.first()
    assert plan_cost.subscriptions.count() == 2
    _ = create_venmo_user(django_user_model, user=jane)

    manager.process_subscriptions()
    assert manager.venmo_client.payment.request_money.call_count == 2
    assert Bill.objects.count() == 2


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
        manager.venmo_client.user.get_user_transactions = Mock(return_value=[mock_txn])

    assert Payment.objects.count() == 0
    manager.process_subscriptions()
    assert Payment.objects.count() == expected_transactions

    # If a transaction was matched, the sub's next billing date should be moved out
    latest_sub = models.UserSubscription.objects.get(id=sub.id)
    if expected_transactions:
        txn = Payment.objects.first()
        assert txn.amount == mock_txn.amount
        assert txn.user == bill.user
        assert txn.subscription == bill.subscription
        assert txn.date_transaction == datetime.fromtimestamp(mock_txn.date_completed, tz=timezone.utc)
        assert txn.amount == bill.amount
        assert txn.host_payment_id == mock_txn.id
        assert txn.data is not None and len(txn.data.keys()) > 0

        assert latest_sub.date_billing_next > initial_billing_next
    else:
        assert latest_sub.date_billing_next == initial_billing_next


def test_due_subscriber_pay_match(manager, bill, venmo_user):
    """Ensures that when subscriber pays us for the expected cost, it gets matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount, actor=venmo_subscriber, target=MOCK_PROFILE_VENMO_USER, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 1)

def test_due_subscriber_charge_match(manager, bill, venmo_user):
    """Ensures that when subscriber is charged for the expected cost, it gets matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount, payment_type="charge", actor=MOCK_PROFILE_VENMO_USER, target=venmo_subscriber, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 1)

def test_due_subscriber_pay_wrong_amount_nomatch(manager, bill, venmo_user):
    """Ensures that when subscriber pays us for an unexpected cost, it doesn't get matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount + 1, actor=venmo_subscriber, target=MOCK_PROFILE_VENMO_USER, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 0)

def test_due_subscriber_charge_wrong_amount_nomatch(manager, bill, venmo_user):
    """Ensures that when subscriber is charged for an unexpected cost, it doesn't get matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount - Decimal(.5), payment_type="charge", actor=MOCK_PROFILE_VENMO_USER, target=venmo_subscriber, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 0)

def test_due_root_pay_nomatch(manager, bill, venmo_user):
    """Ensures that when root pays subscriber for plan cost, it doesn't get matched."""
    venmo_subscriber = _venmo_account_to_api_model(venmo_user)
    txn = _create_txn(bill.amount, actor=MOCK_PROFILE_VENMO_USER, target=venmo_subscriber, date_completed=bill.date_transaction)
    _process_and_verify(manager, bill, txn, 0)

def test_due_multiple_subscriptions_processed(manager, django_user_model):
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
    manager.venmo_client.user.get_user_transactions = Mock(return_value=[john_charge_match, jane_pay_nomatch])

    assert Bill.objects.count() == 0
    assert models.SubscriptionTransaction.objects.count() == 0
    assert Payment.objects.count() == 0

    manager.process_subscriptions()

    assert Bill.objects.count() == 2
    assert manager.venmo_client.payment.request_money.call_count == 2 # sent out 2 Bills
    assert Payment.objects.count() == 1 # only matched/saved 1 transaction

    # John paid... so his subscription was updated
    latest_john_sub = models.UserSubscription.objects.get(id=john_sub.id)
    assert initial_john_billing_next < latest_john_sub.date_billing_next

    # Jane still hasn't paid... so her subscription is the same
    latest_jane_sub = models.UserSubscription.objects.get(id=jane_sub.id)
    assert initial_jane_billing_next == latest_jane_sub.date_billing_next

    # We only called out to Venmo to get transactions once (and cached result)
    manager.venmo_client.user.get_user_transactions.assert_called_once()

def test_due_shared_venmo_accounts(manager, django_user_model):
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
    manager.venmo_client.user.get_user_transactions = Mock(return_value=[john_charge_match, jane_charge_match])

    manager.process_subscriptions()
    assert Bill.objects.count() == 2
    assert Payment.objects.count() == 2

def test_due_cancels_after_grace_period(manager, due_subscription, venmo_user):
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
    assert Payment.objects.count() == 0
    manager.venmo_client.payment.request_money.assert_called_once()

    # google integration was disabled... so shouldn't have been called.
    manager.google_client.people.assert_not_called()


def _init_google_mocks(manager, contact_label, email):
    mock_people = Mock()
    manager.google_client.people = Mock(return_value=mock_people)

    mock_search_contacts = Mock()
    mock_people.searchContacts = Mock(return_value=mock_search_contacts)

    mock_search_result = {
        'results': [
            {
                'person': {
                    'resourceName': 'people/1234',
                }
            }
        ]
    }
    mock_search_contacts.execute = Mock(return_value=mock_search_result)


def test_due_cancels_after_grace_period_google_enabled(manager, due_subscription, venmo_user):
    # Initial process_subscriptions sets billing_end date, but doesn't expire it
    manager.process_subscriptions()

    # This process_subscriptions sees that billing_end date is past grace period, and will both
    # expire it and remove contact label from Google (since enabled)
    test_contact_label = "abcdefg"
    google.GOOGLE_CONTACT_GROUP_ID = test_contact_label
    _init_google_mocks(manager, test_contact_label, due_subscription.user.email)
    try:
        manager.process_subscriptions()
    finally:
        google.GOOGLE_CONTACT_GROUP_ID = None

    # google integration was disabled... so shouldn't have been called.
    manager.google_client.people().searchContacts.assert_called_once()
    manager.google_client.contactGroups().members().modify().execute.assert_called_once()

def test_due_resets_after_payment(manager, due_subscription, venmo_user):
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
