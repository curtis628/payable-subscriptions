"""Django management command to print latest subscription details."""
# see: https://docs.djangoproject.com/en/4.1/howto/custom-management-commands/
import logging

from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from subscriptions.models import UserSubscription

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        cost = options["cost"]
        include_inactive = options["include_inactive"]
        logger.debug(f"Processing request with cost={cost} include-inactive={include_inactive}")

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
