"""
notification-relay — Firebase Cloud Functions entry point.

Deployment:
    firebase deploy --only functions

See docs/RULE_SCHEMA.md for the Condition/Rule schema shared with the
Android app, and the plan file for the overall architecture.
"""

# Populated as each module is built (see build order in the plan):
#   from ingest import ingest_notification
#   from devices_callables import update_device_rules, list_device_rules, report_installed_apps
#   from subscribers_callables import create_subscriber, grant_subscriber_access, \
#       revoke_subscriber_access, list_subscribers, disable_subscriber, purge_expired_subscribers
#   from webhooks_api import webhooks_api
#   from webhooks_admin_callables import list_all_webhooks
#   from test_receiver import test_receiver
