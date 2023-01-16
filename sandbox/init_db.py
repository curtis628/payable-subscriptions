import csv
import os
from decimal import Decimal
from datetime import timedelta

from getpass import getpass
from venmo_api import Client
from django.utils import timezone
from django.contrib.auth.models import User, Group
from subscriptions.models import PlanTag, SubscriptionPlan, PlanCost, MONTH, YEAR, ONCE, PlanList, PlanListDetail, UserSubscription
from payablesubs.models import VenmoAccount

TOKEN_KEY = "VENMO_ACCESS_TOKEN"

SUBSCRIBER_GROUP = "Subscribers"
GRACE_DAYS = 7
STANDARD_PLAN = "Flimm"
MANUAL_PLAN = "Manual"
FREE_PLAN = "Free"

password="testPASS123"
subscriber_group, _= Group.objects.get_or_create(name=SUBSCRIBER_GROUP)
public_tag, _=PlanTag.objects.get_or_create(tag="public")
hidden_tag, _=PlanTag.objects.get_or_create(tag="hidden")
std_plan = SubscriptionPlan.objects.filter(plan_name=STANDARD_PLAN).first()
if not std_plan:
    std_plan = SubscriptionPlan(
        plan_name="Flimm",
        plan_description="Normal, paying plan",
        group=subscriber_group,
        grace_period=GRACE_DAYS,
    )
    std_plan.save()
    std_plan.tags.add(public_tag)
    std_plan.save()
    PlanCost.objects.create(
        plan=std_plan,
        recurrence_period=1,
        recurrence_unit=MONTH,
        cost=Decimal(2)
    )
    PlanCost.objects.create(
        plan=std_plan,
        recurrence_period=6,
        recurrence_unit=MONTH,
        cost=Decimal(12)
    )
    PlanCost.objects.create(
        plan=std_plan,
        recurrence_period=1,
        recurrence_unit=YEAR,
        cost=Decimal(24)
    )
    plan_list, _= PlanList.objects.get_or_create(
        title="The Flimm",
        subtitle="Brief. Relevant. Entertaining.",
        header="",
        footer=""
    )
    PlanListDetail.objects.get_or_create(
        plan=std_plan,
        plan_list=plan_list,
        html_content=""
    )

std_plan_cost = std_plan.costs.first()
free_plan = SubscriptionPlan.objects.filter(plan_name=FREE_PLAN).first()
if not free_plan:
    free_plan = SubscriptionPlan.objects.create(
        plan_name="Free",
        plan_description="Reserved for very special people...",
        group=subscriber_group,
    )
    free_plan.tags.add(hidden_tag)
    free_plan.save()
    PlanCost.objects.create(
        plan=free_plan,
        recurrence_period=1,
        recurrence_unit=ONCE,
        cost=Decimal(0)
    )

free_plan_cost = free_plan.costs.first()
username_to_venmo_usernames = {}
now = timezone.now()
next_bill = now + timedelta(days=30)
access_token = os.environ[TOKEN_KEY] if TOKEN_KEY in os.environ else getpass("Venmo Access Token: ")
client = Client(access_token)
with open('initial_users.csv', newline='') as csvfile:
    csv_reader = csv.reader(csvfile)
    for row in csv_reader:
        first_name, last_name, email, venmo_username = row
        username=email
        user = User.objects.create_user(username, None, password)
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.groups.add(subscriber_group)
        user.save()
        print(f"Created {user}: {first_name} {last_name}")
        UserSubscription.objects.create(
            user=user,
            subscription=std_plan_cost,
            date_billing_start=now,
            date_billing_end=None,
            date_billing_last=now,
            date_billing_next=next_bill
        )
        if "N/A" != venmo_username:
            from_venmo = client.user.get_user_by_username(venmo_username)
            VenmoAccount.objects.create( user=user, venmo_username=venmo_username, venmo_id=from_venmo.id)
            username_to_venmo_usernames[email] = venmo_username


for free_user_email in ["lindy", "taryn"]:
    user = User.objects.get(email__startswith=free_user_email)
    UserSubscription.objects.filter(user=user).delete()
    UserSubscription.objects.create(
        user=user,
        subscription=free_plan_cost,
        date_billing_start=now,
        date_billing_end=None,
        date_billing_last=None,
        date_billing_next=None
    )

for real_user_email in ["tyler", "mal", "lauren", "will"]:
    user = User.objects.get(email__startswith=real_user_email)
    UserSubscription.objects.filter(user=user).delete()
    UserSubscription.objects.create(
        user=user,
        subscription=std_plan_cost,
        date_billing_start=now,
        date_billing_end=None,
        date_billing_last=now,
        date_billing_next=next_bill
    )