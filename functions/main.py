"""
notification-relay — Firebase Cloud Functions entry point.

Deployment:
    firebase deploy --only functions

See docs/RULE_SCHEMA.md for the Condition/Rule schema shared with the
Android app, and the plan file for the overall architecture.
"""

from access_requests_api import access_requests_api  # noqa: F401
from access_requests_callables import (  # noqa: F401
    approve_access_request,
    deny_access_request,
    list_access_requests,
)
from devices_callables import (  # noqa: F401
    list_device_rules,
    list_devices,
    report_device_status,
    update_device_rules,
)
from ingest import ingest_notification  # noqa: F401
from subscribers_callables import (  # noqa: F401
    create_subscriber,
    delete_subscriber,
    disable_subscriber,
    grant_subscriber_access,
    list_subscribers,
    purge_expired_subscribers,
    revoke_subscriber_access,
)
from webhooks_admin_callables import list_all_webhooks, list_delivery_log  # noqa: F401
from webhooks_api import webhooks_api  # noqa: F401
from test_receiver import test_receiver  # noqa: F401
