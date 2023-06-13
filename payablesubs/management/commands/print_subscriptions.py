"""Django management command to print latest subscription details."""
# see: https://docs.djangoproject.com/en/4.1/howto/custom-management-commands/
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from subscriptions.models import UserSubscription

logger = logging.getLogger(__name__)
timezone = ZoneInfo(settings.TIME_ZONE)


class Command(BaseCommand):
    """Django management command to print latest subscription details."""

    _ALL = "ALL"  # all PlanCost instances, regardless of cost
    _FREE = "FREE"  # only PlanCost instances with 0 cost
    _PAYING = "PAYING"  # only PlanCost instances with > 0 cost

    help = "Prints latest subscription details"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cost",
            choices=[Command._PAYING, Command._FREE, Command._ALL],
            help=_("Print subscriptions matching this cost"),
            default=Command._PAYING,
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help=_("Include inactive subscriptions in the report"),
        )
        parser.add_argument(
            "--email-to",
            help=_("The email address to send the subscription details to"),
        )

    def handle(self, *args, **options):
        cost = options["cost"]
        include_inactive = options["include_inactive"]
        email_to = options["email_to"]
        logger.debug(f"Processing request with {cost=} {include_inactive=} {email_to=}")

        subs = UserSubscription.objects.all().order_by("-subscription__cost", "user__email")
        if include_inactive:
            logger.warning("Including inactive subscriptions in report!")
        else:
            subs = subs.filter(active=True)

        if cost == Command._PAYING:
            subs = subs.filter(subscription__cost__gt=0)
        elif cost == Command._FREE:
            subs = subs.filter(subscription__cost=0)

        sub_strs = [f"{sub}" for sub in subs]
        big_str = "\n".join(sub_strs)
        logger.info(f"There are {len(subs)} subscriptions using {cost=}:\n{big_str}")

        if email_to:
            now = datetime.now(tz=timezone)
            subject = f"[TheFlimm] {now.strftime('%B %Y')} has {len(subs)} {cost.lower()} subscribers"
            logger.info(f"Sending email with {subject=} to {email_to}")
            send_mail(subject, big_str, None, [email_to])
