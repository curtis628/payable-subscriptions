"""Django management command to add subscriptions via task runner."""
# see: https://docs.djangoproject.com/en/4.1/howto/custom-management-commands/
import logging
import os
from datetime import date
from decimal import Decimal
from getpass import getpass

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from subscriptions.models import SubscriptionPlan, UserSubscription
from venmo_api import Client

from payablesubs.management.commands._payable_manager import TOKEN_KEY
from payablesubs.models import VenmoAccount

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command to add subscriptions via task runner."""

    help = "Automates adding a new user + subscription."

    def __init__(self, client=None):
        self.client = client
        if not client:
            logger.debug("Initializing Venmo client...")
            access_token = os.environ[TOKEN_KEY] if TOKEN_KEY in os.environ else getpass("Venmo Access Token: ")
            self.client = Client(access_token)

    def add_arguments(self, parser):
        parser.add_argument("first_name")
        parser.add_argument("last_name")
        parser.add_argument("email")
        parser.add_argument("plan", help=_("The name of the plan to add user's subscription to"))
        parser.add_argument(
            "start_date", type=lambda d: date.fromisoformat(d), help=_("The start date of subscription: YYYY-mm-dd")
        )
        parser.add_argument(
            "--cost",
            type=Decimal,
            help=("Subscribe to the PlanCost that has this recurring cost. Defaults to first if not provided"),
        )
        parser.add_argument("--venmo-username")

    def handle(self, *args, **options):
        """Runs logic to add a given user."""
        first_name = options["first_name"]
        last_name = options["last_name"]
        email = options["email"]
        plan_name = options["plan"]
        start_date = options["start_date"]
        args_cost = options["cost"]
        venmo_username = options["venmo_username"]
        logger.info(f"Adding subscriber using:\n{options}")

        user = User.objects.filter(email=email).first()
        if not user:
            logger.debug(f"User with {email} doesn't exist. Creating a new user...")
            password = getpass()
            user = User.objects.create_user(
                username=email, first_name=first_name, last_name=last_name, email=email, password=password
            )

        plan = SubscriptionPlan.objects.filter(plan_name=plan_name).first()
        if not plan:
            raise RuntimeError(f"No '{plan_name}' SubscriptionPlan found.")

        plan_costs = plan.costs
        if not plan_costs:
            raise RuntimeError(f"No PlanCost exists for '{plan_name}' SubscriptionPlan.")

        if args_cost and not plan_costs.filter(cost=args_cost):
            raise RuntimeError(f"No PlanCost exists for '{plan_name}' with cost={args_cost}.")

        plan_cost = plan_costs.first() if not args_cost else plan_costs.filter(cost=args_cost).first()
        new_sub = UserSubscription.objects.create(
            user=user,
            subscription=plan_cost,
            date_billing_start=start_date,
            date_billing_end=None,
            date_billing_last=None,
            date_billing_next=start_date,
        )

        if venmo_username:
            logger.debug(f"Storing {user}'s {venmo_username=} ...")
            from_venmo = self.client.user.get_user_by_username(venmo_username)
            venmo_acct = VenmoAccount.objects.create(user=user, venmo_username=venmo_username, venmo_id=from_venmo.id)
            logger.info(f"Created {venmo_acct}")

        logger.info(f"Created new '{new_sub}'")
