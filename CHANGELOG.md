# CHANGELOG

## In Development
* Improve charge request's `note` to include start/end dates for multi-month subscriptions

## 1.0.2
* `Payment` model extends `django-flexible-subscriptions` `SubscriptionTransaction`.
  This supports Venmo + cash payments, while still integrating with their existing transaction UI
* Add setting `PAYABLESUBS_BILLING_ENABLED` to allow disabling Venmo requests.
  This is helpful during testing...

## 1.0.1

* Initial release!
