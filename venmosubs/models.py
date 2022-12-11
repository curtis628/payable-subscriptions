from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _
from subscriptions.models import PlanCost, SubscriptionTransaction


class VenmoTransaction(SubscriptionTransaction):
    """Stores the Venmo-backend ID for payments, in addition to other `SubscriptionTransaction` fields."""

    venmo_id = models.PositiveBigIntegerField(
        editable=False,
        unique=True,
        verbose_name="Venmo ID",
    )


class Bill(models.Model):
    """Track bills in a separate table - but it includes the same fields as the transaction."""

    id = models.UUIDField(
        default=uuid4,
        editable=False,
        primary_key=True,
        verbose_name="ID",
    )
    user = models.ForeignKey(
        get_user_model(),
        help_text=_("the user that this subscription was billed for"),
        null=True,
        on_delete=models.SET_NULL,
        # related_name="subscription_transactions",
    )
    subscription = models.ForeignKey(
        PlanCost,
        help_text=_("the plan costs that were billed"),
        null=True,
        on_delete=models.SET_NULL,
        # related_name="transactions",
    )
    date_transaction = models.DateTimeField(
        help_text=_("the datetime the transaction was billed"),
        verbose_name="transaction date",
    )
    amount = models.DecimalField(
        blank=True,
        decimal_places=4,
        help_text=_("how much was billed for the user"),
        max_digits=19,
        null=True,
    )

    class Meta:
        ordering = (
            "date_transaction",
            "user",
        )

    def __str__(self):
        return f"user={self.user} plan_cost={self.subscription} due={self.date_transaction}"


class VenmoAccount(models.Model):
    """Stores Venmo details for a user"""

    user = models.OneToOneField(
        get_user_model(),
        help_text=_("the user associated with this Venmo account"),
        null=True,
        on_delete=models.CASCADE,
        unique=True,
    )

    venmo_id = models.CharField(max_length=64)
    venmo_username = models.CharField(max_length=64)

    def __str__(self):
        return f"user={self.user} venmo_username={self.venmo_username} venmo_id={self.venmo_id}"
