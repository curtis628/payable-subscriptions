# venmo-subscriptions
A subscription management system integrated with Venmo requests and payments.

A combination of [django-flexible-subscriptions](https://github.com/studybuffalo/django-flexible-subscriptions)
and [Venmo](https://github.com/mmohades/Venmo) python packages. This gives us a subscription and recurrent billing
system that leverages Venmo as the payment provider.

Quick start
-----------

1. Add "venmosubs" to your `INSTALLED_APPS` setting like this:

```
    INSTALLED_APPS = [
        ...
        'venmosubs',
    ]
```

2. Include the polls URLconf in your project `urls.py` like this:

```
   path('subscriptions/', include('subscriptions.urls')),
```

3. Run ``python manage.py migrate`` to create the models.

4. Start the development server and visit http://127.0.0.1:8000/subscriptions/dfs/subscriptions
   to view the subscriptions dashboard. NOTE: You need to create and login with a superuser account.
