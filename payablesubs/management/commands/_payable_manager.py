"""Provides OOTB support to use Venmo for processing and requesting payments"""
import logging
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db.models import Q
from subscriptions.management.commands._manager import Manager

import payablesubs.clients.google as google
import payablesubs.clients.venmo as venmo
from payablesubs.models import Bill, Payment, VenmoAccount

logger = logging.getLogger(__name__)


def _txn_tostring(t):
    """Helper __str__ method to print out Venmo `Transaction` API model object passed in `t`."""
    return (
        f"{t.actor.username:19} {t.payment_type:6} {t.amount:6} to {t.target.username:19} "
        f"on {datetime.fromtimestamp(t.date_completed, tz=timezone.utc)} for '{t.note}'"
    )


class PayableManager(Manager):
    """Extends `Manager` functionality with Venmo payments and requests."""

    def __init__(self, venmo_client=None, google_client=None):
        self.venmo_client = venmo_client
        self.venmo_txns = []
        if not venmo_client:
            self.venmo_client = venmo.get_client()

        self.google_client = google_client
        if not google_client:
            self.google_client = google.get_client()

    def _generate_note(self, sub):
        plan_cost = sub.subscription
        bill_end = plan_cost.next_billing_datetime(sub.date_billing_next)

        # Massaging billing start/end dates if they are close to month's boundaries
        # i.e.: A monthly bill that starts on 2/28 should be for the month of Mar; not Feb.
        adjusted_begin_date = sub.date_billing_next + timedelta(days=7)
        adjusted_bill_end = bill_end - timedelta(days=7)
        duration = adjusted_begin_date.strftime("%b")
        diff = bill_end - sub.date_billing_next
        if diff.days > 33:  # only include bill's end month if subscription is for > 1 months
            duration += " - " + adjusted_bill_end.strftime("%b")
        duration += adjusted_bill_end.strftime(" %Y")
        note = f"{sub.user.first_name}'s {plan_cost.plan.plan_name} subscription for {duration}"
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
            if settings.PAYABLESUBS_BILLING_ENABLED and not settings.PAYABLESUBS_DRY_RUN:
                logger.debug(f"Sending Venmo request with note: {note}")
                self.venmo_client.payment.request_money(float(amount_due), note, venmo_account.venmo_id)
            else:
                logger.warning(f"Billing feature disabled. Not sending bill with note: {note}")
            bill = Bill(user=user, subscription=plan_cost, amount=amount_due, date_transaction=sub.date_billing_next)
            if not settings.PAYABLESUBS_DRY_RUN:
                bill.save()

        return bill

    @staticmethod
    def _parse_txn_data(txn):
        """Parse out `Payment.data` Venmo fields we want to persist in our backend."""
        payer = txn.actor if txn.payment_type == "pay" else txn.target
        return {
            "venmo_id": str(payer.id),
            "venmo_username": payer.username,
            "amount": txn.amount,
            "payment_type": txn.payment_type,
            "date_created": txn.date_created,
            "date_updated": txn.date_updated,
            "date_completed": txn.date_completed,
        }

    def _check_payments(self, sub, current_bill):
        """Looks through recent `txns` to see if `current_bill` has been paid already."""
        # populate recent venmo txns if we haven't already
        if not self.venmo_txns:
            venmo_profile = self.venmo_client.my_profile()
            logger.info(f"Populating recent transactions associated with {venmo_profile.username}...")
            txns = self.venmo_client.user.get_user_transactions(venmo_profile.id)

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
            txn_strs = [f"{_txn_tostring(t)}" for t in self.venmo_txns]
            big_txn_str = "\n".join(txn_strs)
            logger.debug(f"{len(self.venmo_txns)} / {len(txns)} from VENMO are payments to us.\n{big_txn_str}")

        last_payment = Payment.objects.filter(user=sub.user).order_by("-date_transaction").first()
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
            already_matched_txn = Payment.objects.filter(host_payment_id=t.id).first()
            if already_matched_txn:
                logger.warning(f"Already matched Payment {t.id=}: {_txn_tostring(t)}")
            else:
                return Payment(
                    host_payment_id=t.id,
                    subscription=sub.subscription,
                    user=sub.user,
                    amount=sub.subscription.cost,
                    method=Payment.PaymentMethod.VENMO,
                    date_transaction=datetime.fromtimestamp(t.date_completed, tz=timezone.utc),
                    data=PayableManager._parse_txn_data(t),
                )
        return None

    def process_due(self, subscription):
        bill = self._get_or_create_bill(subscription)
        logger.debug(f"Processing due {subscription=} {bill=}")
        matched_txn = self._check_payments(subscription, bill)

        if settings.PAYABLESUBS_DRY_RUN:
            logger.warning(f"Not updating subscription or saving matched {matched_txn} while in 'dry run' mode...")
        elif matched_txn:
            # Update subscription details
            matched_txn.save()
            cost = subscription.subscription
            next_billing = cost.next_billing_datetime(subscription.date_billing_next)
            subscription.date_billing_last = matched_txn.date_transaction
            subscription.date_billing_next = next_billing
            subscription.date_billing_end = None
            subscription.save()
            logger.info(f"{subscription} payment={matched_txn} processed successfully")
        else:
            sub_end_date = subscription.date_billing_end
            grace_days = subscription.subscription.plan.grace_period
            end_dt = sub_end_date if sub_end_date else subscription.date_billing_next + timedelta(days=grace_days)
            logger.info(f"{subscription} will automatically end on {end_dt}")

            if not subscription.date_billing_end:
                subscription.date_billing_end = end_dt
                subscription.save()

    def notify_expired(self, subscription):
        # remove subscribed user of the associated label in Google contacts
        email = subscription.user.email
        logger.debug(f"Processing expired {subscription}: [{email=}]")
        google.remove_contact_label(subscription.user, client=self.google_client)
        logger.info(f"Successfully removed {email} from Google")
