from enum import Enum


class AEContextType(str, Enum):
    permission = "Permission"
    directory = "Directory"
    workspace = "WorkSpace"
