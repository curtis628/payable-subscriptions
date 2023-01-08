# CHANGELOG

## In Development

## 1.0.002
* `Payment` model extends `django-flexible-subscriptions` `SubscriptionTransaction`.
  This supports Venmo + cash payments, while still integrating with their existing transaction UI
* Add setting `PAYABLESUBS_BILLING_ENABLED` to allow disabling Venmo requests.
  This is helpful during testing...

## 1.0.001

* Initial release!
