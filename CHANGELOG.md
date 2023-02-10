# CHANGELOG

## In Development

## 1.0.6
* Integrate with Google APIs for managing contact group associated with active subscriptions.
* Cleanup Venmo client initialization
  * Consolidate to `clients/venmo.py`
  * Remove env variable support in favor of `.credentials/venmo.token`

## 1.0.5
* Implement `add_subscription` custom command to facilitate adding new subscriptions
* Add setting `PAYABLESUBS_DRY_RUN` to allow running without worrying it about
  it affecting any data or sending payment requests.
 
## 1.0.4
* Has bug. Do not use.

## 1.0.3
* Improve charge request's `note` to include start/end dates for multi-month subscriptions

## 1.0.2
* `Payment` model extends `django-flexible-subscriptions` `SubscriptionTransaction`.
  This supports Venmo + cash payments, while still integrating with their existing transaction UI
* Add setting `PAYABLESUBS_BILLING_ENABLED` to allow disabling Venmo requests.
  This is helpful during testing...

## 1.0.1

* Initial release!
