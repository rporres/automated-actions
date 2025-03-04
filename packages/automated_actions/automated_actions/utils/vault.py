import os
from collections.abc import Mapping
from pathlib import Path

import hvac
from hvac.api.auth_methods import Kubernetes
from sretoolbox.utils import retry


class SecretNotFoundError(Exception):
    pass


class SecretAccessForbiddenError(Exception):
    pass


class SecretVersionIsNoneError(Exception):
    pass


class SecretVersionNotFoundError(Exception):
    pass


class SecretFieldNotFoundError(Exception):
    pass


class VaultClientBadArgsError(Exception):
    pass


VERSION_1 = 1
VERSION_2 = 2
SECRET_VERSION_LATEST = "LATEST"  # noqa: S105


class VaultClient:
    """A class representing a Vault client. Allows read operations."""

    def __init__(
        self,
        server: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
        kube_auth_role: str | None = None,
        kube_auth_mount: str | None = None,
    ) -> None:
        self._client = hvac.Client(url=server)

        if role_id is not None and secret_id is not None:
            self._client.auth.approle.login(
                role_id=role_id,
                secret_id=secret_id,
            )
        elif kube_auth_role is not None and kube_auth_mount is not None:
            kube_sa_token_path = os.environ.get(
                "KUBE_SA_TOKEN_PATH",
                "/var/run/secrets/kubernetes.io/serviceaccount/token",
            )
            jwt = Path(kube_sa_token_path).read_text(encoding="locale")
            Kubernetes(self._client.adapter).login(
                role=kube_auth_role, jwt=jwt, mount_point=kube_auth_mount
            )
        else:
            raise VaultClientBadArgsError

    @retry()
    def read(self, secret: Mapping) -> str:
        """Returns a value of a key in a Vault secret.

        The input secret is a dictionary which contains the following fields:
        * path - path to the secret in Vault
        * field - the key to read from the secret
        * version (optional) - secret version to read (if this is a v2 KV engine)
        """
        secret_path = secret["path"]
        secret_field = secret["field"]
        secret_version = secret.get("version")

        kv_version = self._get_mount_version_by_secret_path(secret_path)

        data = None
        if kv_version == VERSION_2:
            data = self._read_v2(secret_path, secret_field, secret_version)
        else:
            data = self._read_v1(secret_path, secret_field)

        if data is None:
            raise SecretNotFoundError

        return data

    def _read_v2(self, path: str, field: str, version: str) -> str:
        data, _ = self._read_all_v2(path, version)
        try:
            secret_field = data[field]
        except KeyError:
            raise SecretFieldNotFoundError(f"{path}/{field} ({version})") from None
        return secret_field

    def _read_v1(self, path: str, field: str) -> str:
        data = self._read_all_v1(path)
        try:
            secret_field = data[field]
        except KeyError:
            raise SecretFieldNotFoundError(f"{path}/{field}") from None
        return secret_field

    def _read_all_v2(self, path: str, version: str | None) -> tuple[dict, str | None]:
        path_split = path.split("/")
        mount_point = path_split[0]
        read_path = "/".join(path_split[1:])
        if version is None:
            msg = f"version can not be null for secret with path '{path}'."
            raise SecretVersionIsNoneError(msg)
        if version == SECRET_VERSION_LATEST:
            # https://github.com/hvac/hvac/blob/
            # ec048ded30d21c13c21cfa950d148c8bfc1467b0/
            # hvac/api/secrets_engines/kv_v2.py#L85
            version = None
        try:
            secret = self._client.secrets.kv.v2.read_secret_version(
                mount_point=mount_point,
                path=read_path,
                version=version,
            )
        except hvac.exceptions.InvalidPath:
            msg = f"version '{version}' not found for secret with path '{path}'."
            raise SecretVersionNotFoundError(msg) from None
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing secret '{path}'"
            raise SecretAccessForbiddenError(msg) from None
        if secret is None or "data" not in secret or "data" not in secret["data"]:
            raise SecretNotFoundError(path)

        data = secret["data"]["data"]
        secret_version = secret["data"]["metadata"]["version"]
        return data, secret_version

    def _read_all_v1(self, path: str) -> dict:
        try:
            secret = self._client.read(path)
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing secret '{path}'"
            raise SecretAccessForbiddenError(msg) from None

        if secret is None or "data" not in secret:
            raise SecretNotFoundError(path)

        return secret["data"]

    def _get_mount_version_by_secret_path(self, path: str) -> int:
        path_split = path.split("/")
        mount_point = path_split[0]
        return self._get_mount_version(mount_point)

    def _get_mount_version(self, mount_point: str) -> int:
        try:
            self._client.secrets.kv.v2.read_configuration(mount_point)
            version = VERSION_2
        except Exception:  # noqa: BLE001
            version = VERSION_1

        return version
