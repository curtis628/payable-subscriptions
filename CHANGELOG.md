# CHANGELOG

## In Development
* Incorporate email support to `print_subscriptions` custom command
* Use `America/Los_Angeles` timezone for user interface

## 1.0.7
* Implement `print_subscriptions` custom command for printing subscription reports
* Improved log formatting of applicable Venmo transactions
* Created `refresh-tokens.sh` (though it's hidden from source-control under `./credentials` folder)
  * NOTE: Google client now leveraging Google Workspace

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
