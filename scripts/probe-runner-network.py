"""Resolve and positively connect to targets from the runner's network namespace."""

import json
import socket

TARGETS = (
    ("application_api", "backend", 8000),
    ("database", "mysql", 3306),
    ("external_peer", "network-probe", 9090),
)


def main() -> None:
    targets = []
    for name, hostname, port in TARGETS:
        address = socket.gethostbyname(hostname)
        with socket.create_connection((address, port), timeout=2):
            pass
        targets.append({"name": name, "address": address, "port": port})
    print(json.dumps(targets, separators=(",", ":")))


if __name__ == "__main__":
    main()
