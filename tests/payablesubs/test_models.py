"""Tests for the _venmo_manager module."""
from datetime import datetime, timezone, timedelta
from django.utils import timezone as django_timezone
from django.db.utils import IntegrityError
import uuid
from decimal import Decimal

import pytest

from django.contrib.auth.models import Group

from subscriptions import models
from payablesubs.models import Bill, VenmoAccount, Payment

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


def create_cost(group, plan=None, amount=None, name="Test Plan", desc="This is just a test", grace_days=TEST_PLAN_GRACE_DAYS):
    """Creates and returns a PlanCost instance."""
    if not plan:
        plan = models.SubscriptionPlan.objects.create(
            plan_name=name,
            plan_description=desc,
            group=group,
            grace_period=grace_days
        )
    if not amount:
        amount = Decimal(1)

    return models.PlanCost.objects.create(
        plan=plan, recurrence_period=1, recurrence_unit=models.MONTH, cost=amount
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

def test_cash_payment_creation(django_user_model):
    sub = _setup_subscription(django_user_model)

    cash_payment = Payment.objects.create(
        host_payment_id=123456,
        subscription=sub.subscription,
        user=sub.user,
        amount=sub.subscription.cost,
        method=Payment.PaymentMethod.CASH,
        date_transaction=django_timezone.now(),
    )
    assert str(sub.user) in str(cash_payment)

def test_venmo_duplicate_host_payment_id(django_user_model):
    sub = _setup_subscription(django_user_model)
    host_payment_id=123456
    data = {"venmo_id": 123456789, "user": "test-venmo-user"}

    Payment.objects.create(
        host_payment_id=host_payment_id,
        subscription=sub.subscription,
        user=sub.user,
        amount=sub.subscription.cost,
        method=Payment.PaymentMethod.VENMO,
        date_transaction=django_timezone.now(),
        data=data,
    )

    # duplicate host_payment_id
    with pytest.raises(IntegrityError) as excinfo:
        Payment.objects.create(
            host_payment_id=host_payment_id,
            subscription=sub.subscription,
            user=sub.user,
            amount=sub.subscription.cost,
            method=Payment.PaymentMethod.VENMO,
            date_transaction=django_timezone.now(),
            data=data,
        )
    assert "UNIQUE constraint failed" in str(excinfo.value)
    assert "host_payment_id" in str(excinfo.value)

def test_payment_method_non_nullable(django_user_model):
    sub = _setup_subscription(django_user_model)
    with pytest.raises(IntegrityError) as excinfo:
        Payment.objects.create( # no method
                host_payment_id=123456,
                subscription=sub.subscription,
                user=sub.user,
                amount=sub.subscription.cost,
                date_transaction=django_timezone.now(),
            )
    assert "NOT NULL constraint failed" in str(excinfo.value)
    assert "method" in str(excinfo.value)

def test_venmo_user_creation(django_user_model):
    assert VenmoAccount.objects.all().count() == 0
    create_venmo_user(django_user_model)
    assert VenmoAccount.objects.all().count() == 1

def test_venmo_user_creation_nonunique_user(django_user_model):
    user, _ = create_user_and_group(django_user_model)
    create_venmo_user(django_user_model, user)
    with pytest.raises(IntegrityError):
        create_venmo_user(django_user_model, user)
