"""Provides OOTB support to use Venmo for processing and requesting payments"""
import logging
import os
from datetime import datetime, timedelta, timezone
from getpass import getpass

from django.db.models import Q
from subscriptions.management.commands._manager import Manager
from venmo_api import Client

from payablesubs.models import Bill, VenmoAccount, VenmoTransaction

logger = logging.getLogger(__name__)

TOKEN_KEY = "VENMO_ACCESS_TOKEN"


def _txn_tostring(t):
    """Helper __str__ method to print out Venmo `Transaction` API model object passed in `t`."""
    return (
        f"{t.actor.username} {t.payment_type} {t.amount} to {t.target.username} for "
        f"'{t.note}' on {datetime.fromtimestamp(t.date_completed, tz=timezone.utc)}"
    )


class PayableManager(Manager):
    """Extends `Manager` functionality with Venmo payments and requests."""

    def __init__(self, client=None):
        self.client = client
        self.venmo_txns = []
        if not client:
            logger.debug("Initializing Venmo client...")
            access_token = os.environ[TOKEN_KEY] if TOKEN_KEY in os.environ else getpass("Venmo Access Token: ")
            self.client = Client(access_token)

    def _generate_note(self, sub):
        plan_cost = sub.subscription
        # if billing_next is close to the next month, we should use the next month's name for the note
        note_month = sub.date_billing_next + timedelta(days=7)
        note = (
            f"{sub.user.first_name}'s {plan_cost.plan.plan_name} subscription for " + f"{note_month.strftime('%B %Y')}"
        )
        return note

    def _get_or_create_bill(self, sub):
        user = sub.user
        plan_cost = sub.subscription
        amount_due = plan_cost.cost
        query_bill = Bill.objects.filter(
            Q(user=user) & Q(subscription=sub.subscription) & Q(date_transaction=sub.date_billing_next)
        )
        if query_bill.count() > 0:
            if query_bill.count() > 1:
                logger.error(f"Found multiple bills for sub={sub}: {query_bill}")
            bill = query_bill.first()
        else:
            venmo_account = VenmoAccount.objects.filter(user=user).first()
            if not venmo_account:
                logger.warning(f"No VenmoAccount details for {user=}")
                return False

            note = self._generate_note(sub)
            logger.debug(f"Sending Venmo request with note: {note}")
            self.client.payment.request_money(float(amount_due), note, venmo_account.venmo_id)
            bill = Bill.objects.create(
                user=user, subscription=plan_cost, amount=amount_due, date_transaction=sub.date_billing_next
            )

        return bill

    def _check_payments(self, sub, current_bill):
        """Looks through recent `txns` to see if `current_bill` has been paid already."""
        # populate recent venmo txns if we haven't already
        if not self.venmo_txns:
            venmo_profile = self.client.my_profile()
            logger.info(f"Populating recent transactions associated with {venmo_profile.username}...")
            txns = self.client.user.get_user_transactions(venmo_profile.id)

            logger.debug(f"Found {len(txns)} VENMO transactions.")
            # for t in txns:
            #     logger.debug(_txn_tostring(t))

            # We only care about "payments" to us, or completed "charges" we initiated...
            # i.e.: We shouldn't match a payment we made to someone, or a charge initiated from someone else.
            self.venmo_txns = [
                t
                for t in txns
                if (t.payment_type == "pay" and t.target.username == venmo_profile.username)
                or (t.payment_type == "charge" and t.actor.username == venmo_profile.username)
            ]
            logger.debug(
                f"{len(self.venmo_txns)} / {len(txns)} from VENMO are payments to us.\n"
                f"{[_txn_tostring(t) for t in self.venmo_txns]}"
            )

        last_payment = (
            VenmoTransaction.objects.filter(subscription=sub.subscription).order_by("-date_transaction").first()
        )
        search_begin_date = last_payment.date_transaction if last_payment else sub.date_billing_start

        venmo_acct = VenmoAccount.objects.filter(user=sub.user).first()
        if not venmo_acct:
            logger.warning(f"There's no Venmo account details for {sub.user}!")
            return False

        matched_txns = [
            t
            for t in self.venmo_txns
            if (
                (t.payment_type == "pay" and t.actor.username == venmo_acct.venmo_username)
                or (t.payment_type == "charge" and t.target.username == venmo_acct.venmo_username)
            )
            and (datetime.fromtimestamp(t.date_completed, tz=timezone.utc) > search_begin_date)
            and (t.amount == float(sub.subscription.cost))
        ]
        logger.debug(
            f"Matched {len(matched_txns)} transactions for {sub=} with {search_begin_date=}:\n"
            f"{[_txn_tostring(t) for t in matched_txns]}"
        )

        for t in matched_txns:
            already_matched_txn = VenmoTransaction.objects.filter(venmo_id=t.id).first()
            if already_matched_txn:
                logger.warning(f"Already matched VenmoTransaction {t.id=}: {_txn_tostring(t)}")
            else:
                return VenmoTransaction(
                    venmo_id=t.id,
                    user=sub.user,
                    subscription=sub.subscription,
                    date_transaction=datetime.fromtimestamp(t.date_completed, tz=timezone.utc),
                    amount=sub.subscription.cost,
                )
        return None

    def process_due(self, subscription):
        bill = self._get_or_create_bill(subscription)
        logger.debug(f"Processing due {subscription=} {bill=}")
        matched_txn = self._check_payments(subscription, bill)

        if matched_txn:
            # Update subscription details
            matched_txn.save()
            cost = subscription.subscription
            next_billing = cost.next_billing_datetime(subscription.date_billing_next)
            subscription.date_billing_last = matched_txn.date_transaction
            subscription.date_billing_next = next_billing
            subscription.date_billing_end = None
            subscription.save()
            logger.info(f"{subscription} payment processed successfully")
        else:
            sub_end_date = subscription.date_billing_end
            grace_days = subscription.subscription.plan.grace_period
            end_dt = sub_end_date if sub_end_date else subscription.date_billing_next + timedelta(days=grace_days)
            logger.info(f"{subscription} will automatically end on {end_dt}")

            if not subscription.date_billing_end:
                subscription.date_billing_end = end_dt
                subscription.save()
