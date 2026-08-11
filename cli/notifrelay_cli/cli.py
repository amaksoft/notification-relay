"""
notifrelay — access-management CLI. See docs/OPERATIONS.md and the plan's
CLI section for the full command reference and the local/remote backend
split.
"""

import argparse
import json
import re
import sys

from . import backend, conditions, remote_backend
from .config import set_default_device_id


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, default=str))


_DURATION_RE = re.compile(r"^(\d+)([smhd])?$")
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, None: 1}


def parse_duration(value: str) -> int:
    match = _DURATION_RE.match(value.strip())
    if not match:
        raise SystemExit(f"Invalid duration {value!r}. Use e.g. 30, 30s, 15m, 1h, 2d.")
    amount, unit = match.groups()
    return int(amount) * _DURATION_UNITS[unit]


def _add_backend_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device-id", help="Device id (falls back to the default set via `device use`).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--local", action="store_const", dest="prefer", const="local")
    group.add_argument("--remote", action="store_const", dest="prefer", const="remote")


def cmd_device_use(args) -> None:
    set_default_device_id(args.device_id)
    print(f"Default device set to {args.device_id}")


def cmd_device_list_apps(args) -> None:
    _print_json(backend.list_installed_apps(args.prefer, args.device_id))


def cmd_device_list_channels(args) -> None:
    _print_json(backend.list_seen_channels(args.prefer, args.device_id, args.package))


def cmd_device_rule_list(args) -> None:
    _print_json(backend.list_rules(args.prefer, args.device_id))


def cmd_device_rule_add(args) -> None:
    condition = conditions.build_simple_condition(
        package=args.package, channel=args.channel,
        title_contains=args.title_contains, text_contains=args.text_contains,
    )
    rule = {"name": args.name, "condition": condition, "throttleSeconds": args.throttle}
    rule_id = backend.add_rule(args.prefer, args.device_id, rule)
    print(f"Added rule {rule_id!r}")


def cmd_device_rule_add_json(args) -> None:
    with open(args.file) as f:
        rule = json.load(f)
    rule_id = backend.add_rule(args.prefer, args.device_id, rule)
    print(f"Added rule {rule_id!r}")


def cmd_device_rule_enable(args) -> None:
    backend.set_rule_enabled(args.prefer, args.device_id, args.rule_id, True)
    print(f"Enabled rule {args.rule_id!r}")


def cmd_device_rule_disable(args) -> None:
    backend.set_rule_enabled(args.prefer, args.device_id, args.rule_id, False)
    print(f"Disabled rule {args.rule_id!r}")


def cmd_device_rule_remove(args) -> None:
    backend.remove_rule(args.prefer, args.device_id, args.rule_id)
    print(f"Removed rule {args.rule_id!r}")


def _parse_grant(spec: str) -> dict:
    package, _, channel = spec.partition(":")
    grant = {"package": package}
    if channel:
        grant["channelIds"] = [channel]
    return grant


def cmd_subscriber_create(args) -> None:
    if args.allow_all:
        grants = {"allowAll": True}
    else:
        merged: dict[str, dict] = {}
        for spec in args.grant or []:
            grant = _parse_grant(spec)
            existing = merged.setdefault(grant["package"], {"package": grant["package"]})
            if "channelIds" in grant:
                existing.setdefault("channelIds", [])
                existing["channelIds"].extend(grant["channelIds"])
        grants = {"grants": list(merged.values())}
    ttl_seconds = parse_duration(args.ttl) if args.ttl else None
    subscriber_id, api_key = remote_backend.create_subscriber(args.name, grants, ttl_seconds)
    print(f"Subscriber id: {subscriber_id}")
    print(f"API key (shown once): {api_key}")


def cmd_subscriber_grant(args) -> None:
    channel_ids = [args.channel] if args.channel else None
    grants = remote_backend.grant_access(args.subscriber_id, args.package, channel_ids)
    _print_json(grants)


def cmd_subscriber_revoke(args) -> None:
    grants = remote_backend.revoke_access(args.subscriber_id, args.package)
    _print_json(grants)


def cmd_subscriber_list(args) -> None:
    _print_json(remote_backend.list_subscribers())


def cmd_subscriber_disable(args) -> None:
    deleted = remote_backend.disable_subscriber(args.subscriber_id)
    print(f"Disabled. Deleted {deleted} webhook(s).")


def cmd_webhook_list(args) -> None:
    _print_json(remote_backend.list_webhooks(args.subscriber_id))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="notifrelay")
    subparsers = parser.add_subparsers(dest="command", required=True)

    device = subparsers.add_parser("device").add_subparsers(dest="device_command", required=True)

    p = device.add_parser("use")
    p.add_argument("device_id")
    p.set_defaults(func=cmd_device_use)

    p = device.add_parser("list-apps")
    _add_backend_flags(p)
    p.set_defaults(func=cmd_device_list_apps)

    p = device.add_parser("list-channels")
    _add_backend_flags(p)
    p.add_argument("--package")
    p.set_defaults(func=cmd_device_list_channels)

    rule = device.add_parser("rule").add_subparsers(dest="rule_command", required=True)

    p = rule.add_parser("list")
    _add_backend_flags(p)
    p.set_defaults(func=cmd_device_rule_list)

    p = rule.add_parser("add")
    _add_backend_flags(p)
    p.add_argument("--name", required=True)
    p.add_argument("--package")
    p.add_argument("--channel")
    p.add_argument("--title-contains")
    p.add_argument("--text-contains")
    p.add_argument("--throttle", type=int, default=0)
    p.set_defaults(func=cmd_device_rule_add)

    p = rule.add_parser("add-json")
    _add_backend_flags(p)
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_device_rule_add_json)

    p = rule.add_parser("enable")
    _add_backend_flags(p)
    p.add_argument("rule_id")
    p.set_defaults(func=cmd_device_rule_enable)

    p = rule.add_parser("disable")
    _add_backend_flags(p)
    p.add_argument("rule_id")
    p.set_defaults(func=cmd_device_rule_disable)

    p = rule.add_parser("remove")
    _add_backend_flags(p)
    p.add_argument("rule_id")
    p.set_defaults(func=cmd_device_rule_remove)

    subscriber = subparsers.add_parser("subscriber").add_subparsers(dest="subscriber_command", required=True)

    p = subscriber.add_parser("create")
    p.add_argument("--name", required=True)
    p.add_argument("--grant", action="append", help="package or package:channelId, repeatable")
    p.add_argument("--allow-all", action="store_true")
    p.add_argument("--ttl", help="e.g. 30m, 1h, 2d")
    p.set_defaults(func=cmd_subscriber_create)

    p = subscriber.add_parser("grant")
    p.add_argument("subscriber_id")
    p.add_argument("--package", required=True)
    p.add_argument("--channel")
    p.set_defaults(func=cmd_subscriber_grant)

    p = subscriber.add_parser("revoke")
    p.add_argument("subscriber_id")
    p.add_argument("--package", required=True)
    p.set_defaults(func=cmd_subscriber_revoke)

    p = subscriber.add_parser("list")
    p.set_defaults(func=cmd_subscriber_list)

    p = subscriber.add_parser("disable")
    p.add_argument("subscriber_id")
    p.set_defaults(func=cmd_subscriber_disable)

    webhook = subparsers.add_parser("webhook").add_subparsers(dest="webhook_command", required=True)
    p = webhook.add_parser("list")
    p.add_argument("--subscriber-id", dest="subscriber_id")
    p.set_defaults(func=cmd_webhook_list)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "prefer"):
        args.prefer = None
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
