import os
import stat
from typing import Dict

from Network.Core import AENetReq
from .AEBaseContext import AEBaseContext


class AEPermissionContext(AEBaseContext):
    paths = []

    def __init__(self, context_info: dict | None = None):
        super().__init__(ident="Permission", context_info=context_info)

    async def handle_request(self, request: AENetReq, connection_id: str) -> None:
        params = self._extract_parameters(request)
        operation = self.resolve_operation(request) or params.get("operation")

        if operation == "check_read":
            return await self._check_read(params)
        if operation == "check_write":
            return await self._check_write(params)
        if operation == "check_exec":
            return await self._check_exec(params)
        if operation == "get_permissions":
            return await self._get_permissions(params)
        return self._create_response(error=f"Unknown operation: {operation}")

    async def _check_read(self, params: Dict[str, object]) -> Dict[str, object]:
        path = params.get("path")
        if not path:
            return self._create_response(error="Path is required")
        valid, error = self.path_validator.validate_path(path)
        if not valid:
            return self._create_response(error=error)
        exists = os.path.exists(path)
        if not exists:
            return self._create_response({"path": path, "exists": False, "readable": False})
        return self._create_response({
            "path": path,
            "exists": True,
            "readable": os.access(path, os.R_OK),
            "is_file": os.path.isfile(path),
            "is_dir": os.path.isdir(path),
        })

    async def _check_write(self, params: Dict[str, object]) -> Dict[str, object]:
        path = params.get("path")
        if not path:
            return self._create_response(error="Path is required")
        valid, error = self.path_validator.validate_path(path)
        if not valid:
            return self._create_response(error=error)
        exists = os.path.exists(path)
        if not exists:
            parent_dir = os.path.dirname(path)
            writable = os.path.exists(parent_dir) and os.access(parent_dir, os.W_OK)
            return self._create_response({
                "path": path,
                "exists": False,
                "writable": writable,
            })
        return self._create_response({
            "path": path,
            "exists": True,
            "writable": os.access(path, os.W_OK),
            "is_file": os.path.isfile(path),
            "is_dir": os.path.isdir(path),
        })

    async def _check_exec(self, params: Dict[str, object]) -> Dict[str, object]:
        path = params.get("path")
        if not path:
            return self._create_response(error="Path is required")
        valid, error = self.path_validator.validate_path(path)
        if not valid:
            return self._create_response(error=error)
        exists = os.path.exists(path)
        if not exists:
            return self._create_response({"path": path, "exists": False, "executable": False})
        return self._create_response({
            "path": path,
            "exists": True,
            "executable": os.access(path, os.X_OK),
            "is_file": os.path.isfile(path),
            "is_dir": os.path.isdir(path),
        })

    async def _get_permissions(self, params: Dict[str, object]) -> Dict[str, object]:
        path = params.get("path")
        if not path:
            return self._create_response(error="Path is required")
        valid, error = self.path_validator.validate_path(path)
        if not valid:
            return self._create_response(error=error)
        if not os.path.exists(path):
            return self._create_response({"path": path, "exists": False})

        file_stat = os.stat(path)
        mode = file_stat.st_mode
        return self._create_response({
            "path": path,
            "exists": True,
            "is_file": os.path.isfile(path),
            "is_dir": os.path.isdir(path),
            "permissions": {
                "readable": os.access(path, os.R_OK),
                "writable": os.access(path, os.W_OK),
                "executable": os.access(path, os.X_OK),
                "owner": {
                    "read": bool(mode & stat.S_IRUSR),
                    "write": bool(mode & stat.S_IWUSR),
                    "execute": bool(mode & stat.S_IXUSR),
                },
                "group": {
                    "read": bool(mode & stat.S_IRGRP),
                    "write": bool(mode & stat.S_IWGRP),
                    "execute": bool(mode & stat.S_IXGRP),
                },
                "others": {
                    "read": bool(mode & stat.S_IROTH),
                    "write": bool(mode & stat.S_IWOTH),
                    "execute": bool(mode & stat.S_IXOTH),
                },
            },
            "octal": oct(stat.S_IMODE(mode)),
            "uid": file_stat.st_uid,
            "gid": file_stat.st_gid,
            "size": file_stat.st_size,
            "modified_time": file_stat.st_mtime,
        })
