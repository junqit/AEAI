import os
from typing import List, Tuple


class AEPathValidator:
    BLACKLIST = [
        "/etc",
        "/sys",
        "/proc",
        "/root",
        "/var/log",
        "/private/etc",
        "/System",
        "/Library/Preferences",
    ]

    def __init__(self, whitelist: List[str]):
        self.whitelist = [os.path.abspath(path) for path in whitelist]

    def validate_path(self, path: str) -> Tuple[bool, str]:
        if not path:
            return False, "Path cannot be empty"

        abs_path = os.path.abspath(path)

        for blacklisted in self.BLACKLIST:
            if abs_path.startswith(blacklisted):
                return False, f"Access to {blacklisted} is forbidden"

        for allowed in self.whitelist:
            if abs_path.startswith(allowed):
                return True, ""

        return False, f"Path {abs_path} is not in whitelist"
