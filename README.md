# payable-subscriptions

[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Code Style](https://img.shields.io/badge/code%20style-isort-blue.svg)](https://github.com/timothycrosley/isort)

--------------
Integrates out-of-the-box payment processing for [django-flexible-subscriptions](https://github.com/studybuffalo/django-flexible-subscriptions).

> Currently, only Venmo is supported.

This builds upon the subscription and recurrent billing from [django-flexible-subscriptions](https://github.com/studybuffalo/django-flexible-subscriptions)
with supported payment vendors, such as Venmo.

## Quick start

1. Add "payablesubs" to your `INSTALLED_APPS` setting like this:

```
    INSTALLED_APPS = [
        ...
        'payablesubs',
    ]
```

2. Include the polls URLconf in your project `urls.py` like this:

```
   path('subscriptions/', include('subscriptions.urls')),
```

3. Run ``python manage.py migrate`` to create the models.

4. Start the development server and visit http://127.0.0.1:8000/subscriptions/dfs/subscriptions
   to view the subscriptions dashboard. NOTE: You need to create and login with a superuser account.


## Libraries Used
* [Venmo API](https://github.com/mmohades/Venmo)