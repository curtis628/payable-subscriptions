"""Tests for the _venmo_manager module."""
from datetime import datetime, timezone, timedelta
from django.utils import timezone as django_timezone
from django.db.utils import IntegrityError
import uuid
from decimal import Decimal

import pytest

from django.contrib.auth.models import Group

from subscriptions import models
from venmosubs.models import Bill, VenmoAccount, VenmoTransaction

TEST_GROUP = "test-group"
TEST_PLAN = "Test Plan"
TEST_PLAN_GRACE_DAYS = 7

pytestmark = pytest.mark.django_db  # pylint: disable=invalid-name


def create_user_and_group(django_user_model, first_name="John", last_name="Doe", group_name=TEST_GROUP):
    group, _ = Group.objects.get_or_create(name=group_name)
    user = django_user_model.objects.create_user(username=f"{first_name.lower()}{last_name.lower()}", first_name=first_name, last_name=last_name, email=f"{first_name}{last_name}@email.com", password="uncrackable:)")
    group.user_set.add(user)
    return user, group


def create_venmo_user(django_user_model, user=None, venmo_username=None, venmo_id=None):
    if not user:
        user, _ = create_user_and_group(django_user_model)
    if not venmo_username:
        venmo_username = f"{user.username}-venmo-username"
    if not venmo_id:
        venmo_id = uuid.uuid4()
    return VenmoAccount.objects.create(user=user, venmo_username=venmo_username, venmo_id=venmo_id)


def create_cost(group, name="Test Plan", desc="This is just a test", grace_days=TEST_PLAN_GRACE_DAYS):
    """Creates and returns a PlanCost instance."""
    plan = models.SubscriptionPlan.objects.create(
        plan_name=name,
        plan_description=desc,
        group=group,
        grace_period=grace_days
    )

    return models.PlanCost.objects.create(
        plan=plan, recurrence_period=1, recurrence_unit=models.MONTH, cost=Decimal(1)
    )


def create_subscription(user, cost=None, group=None, date_start=None, date_next=None, date_end=None):
    if not cost:
        cost = create_cost(group)
    if not date_start:
        # default to beginning of the month
        now = django_timezone.now()
        date_start = datetime(now.year, now.month, 1, now.hour, now.minute, tzinfo=now.tzinfo)
    if not date_next:
        tmp = date_start + timedelta(days=32)
        date_next = datetime(tmp.year, tmp.month, 1, tmp.hour, tmp.minute, tzinfo=tmp.tzinfo)

    return models.UserSubscription.objects.create(
        user=user,
        subscription=cost,
        date_billing_start=date_start,
        date_billing_end=date_end,
        date_billing_last=date_start,
        date_billing_next=date_next,
        active=True,
        cancelled=False,
    )

def create_due_subscription(user, group=None, plan_cost=None):
    """Creates a standard UserSubscription object due for billing."""
    date_start = datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)
    date_next = datetime(2018, 2, 1, 1, 1, 1, tzinfo=timezone.utc)
    return create_subscription(user, plan_cost, group, date_start, date_next)


def _setup_subscription(django_user_model):
    user, group = create_user_and_group(django_user_model)
    return create_subscription(user, group=group)


def test_bill_creation(django_user_model):
    assert Bill.objects.all().count() == 0

    sub = _setup_subscription(django_user_model)
    now = django_timezone.now()
    Bill.objects.create(user=sub.user, subscription=sub.subscription, date_transaction=now, amount=1)
    assert models.SubscriptionTransaction.objects.count() == 0


def test_bill_creation_date_non_nullable(django_user_model):
    sub = _setup_subscription(django_user_model)
    with pytest.raises(IntegrityError) as excinfo:
        Bill.objects.create(user=sub.user, subscription=sub.subscription, date_transaction=None, amount=1)
    assert "NOT NULL constraint failed" in str(excinfo.value)
    assert "date_transaction" in str(excinfo.value)

def test_venmo_transaction_creation(django_user_model):
    sub = _setup_subscription(django_user_model)

    txn = VenmoTransaction.objects.create(
        venmo_id=1234567890123456789,
        user=sub.user,
        subscription=sub.subscription,
        date_transaction=django_timezone.now(),
        amount=sub.subscription.cost
    )
    assert str(sub.user) in str(txn)

def test_venmo_transaction_venmo_id_non_nullable(django_user_model):
    sub = _setup_subscription(django_user_model)
    with pytest.raises(IntegrityError) as excinfo:
        VenmoTransaction.objects.create( # no venmo_id
            user=sub.user,
            subscription=sub.subscription,
            date_transaction=django_timezone.now(),
            amount=sub.subscription.cost
        )

    assert "NOT NULL constraint failed" in str(excinfo.value)
    assert "venmo_id" in str(excinfo.value)

def test_venmo_transaction_venmo_id_is_unique(django_user_model):
    sub = _setup_subscription(django_user_model)
    venmo_id=1234567890123456789

    # First transaction persists fine... but second throws integrity exception
    VenmoTransaction.objects.create(
        venmo_id=venmo_id,
        user=sub.user,
        subscription=sub.subscription,
        date_transaction=django_timezone.now(),
        amount=sub.subscription.cost
    )
    with pytest.raises(IntegrityError) as excinfo:
        VenmoTransaction.objects.create(
            venmo_id=venmo_id,
            user=sub.user,
            subscription=sub.subscription,
            date_transaction=django_timezone.now(),
            amount=sub.subscription.cost
        )

    assert "UNIQUE constraint failed" in str(excinfo.value)
    assert "venmo_id" in str(excinfo.value)

def test_venmo_user_creation(django_user_model):
    assert VenmoAccount.objects.all().count() == 0
    create_venmo_user(django_user_model)
    assert VenmoAccount.objects.all().count() == 1

def test_venmo_user_creation_nonunique_user(django_user_model):
    user, _ = create_user_and_group(django_user_model)
    create_venmo_user(django_user_model, user)
    with pytest.raises(IntegrityError):
        create_venmo_user(django_user_model, user)
