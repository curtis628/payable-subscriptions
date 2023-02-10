# payable-subscriptions

[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Code Style](https://img.shields.io/badge/code%20style-isort-blue.svg)](https://github.com/timothycrosley/isort)

--------------
This builds upon the subscription and recurrent billing from [django-flexible-subscriptions](https://github.com/studybuffalo/django-flexible-subscriptions)
with supported payment vendors, such as Venmo.

* Integrates out-of-the-box payment processing for [django-flexible-subscriptions](https://github.com/studybuffalo/django-flexible-subscriptions).
  * NOTE: Currently, only Venmo is supported.
* Automatically update Google Contact Group based on subscription status (new or expired)

## Quick start

1. Add `payablesubs` (and `subscriptions`) to your `INSTALLED_APPS` setting like this:
```
    INSTALLED_APPS = [
        ...
        'subscriptions',
        'payablesubs',
    ]
```

2. Inject `payablesubs` custom manager class by adding this in settings file:
```
DFS_MANAGER_CLASS = "payablesubs.management.commands._payable_manager.PayableManager"
```

3. Include the polls URLconf in your project `urls.py` like this:
```
   path('subscriptions/', include('subscriptions.urls')),
```

4. Run `python manage.py migrate` to create the models.

5. Start the development server and visit http://127.0.0.1:8000/subscriptions/dfs/subscriptions
   to view the subscriptions dashboard. NOTE: You need to create and login with a superuser account.

   See [django-flexible-subscription documentation](https://django-flexible-subscriptions.readthedocs.io/en/latest/) for more details.

6. Create your Venmo access token following [these instructions](https://github.com/mmohades/Venmo#usage). Save the token to a file: `.credentials/venmo.token`

7. Automate sending and processing payments by calling
```
$> python manage.py process_subscriptions
```

## Optional Settings
The following can be set either directly in your settings file, or via environment properties
* `PAYABLESUBS_BILLING_ENABLED`: if disabled, payment requests will not be sent. Helpful for testing.
* `PAYABLESUBS_DRY_RUN`: processes subscriptions, but doesn't persist `Bill`s or send payment requests. Helpful for testing.
* `PAYABLESUBS_GOOGLE_CONTACT_LABEL`: The Google contact group label associated with active subscriptions. If not set, Google integration is disabled.
  * if enabled, ensure `.credentials/credentials.json` exists. See [Google People Python Quickstart](https://developers.google.com/people/quickstart/python)

## Libraries Used
* [Venmo API](https://github.com/mmohades/Venmo)