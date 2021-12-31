import json
import aiohttp

from loguru import logger

from typing import (
    Optional,
    Dict,
    Any,
    Generic,
    TypeVar,
    Callable,
    Awaitable,
)

from pydantic import BaseModel

from permit.enforcement.interfaces import UserInput
from permit.config import PermitConfig


T = TypeVar("T")


class Tenant(BaseModel):
    key: str
    name: str
    description: Optional[str]


AsyncCallback = Callable[[], Awaitable[Dict]]


class Operation(Generic[T]):
    def __init__(self, callback: AsyncCallback):
        self._callback = callback

    async def run(self) -> T:
        return await self._callback()


class ReadOperation(Operation[Dict]):
    pass


class WriteOperation(Operation[Dict]):
    pass


class ReadApis:
    async def get_user(self, user_key: str) -> ReadOperation:
        raise NotImplementedError("abstract class")

    async def get_role(self, role_key: str) -> ReadOperation:
        raise NotImplementedError("abstract class")

    async def get_tenant(self, tenant_key: str) -> ReadOperation:
        raise NotImplementedError("abstract class")

    async def get_assigned_roles(
        self, user_key: str, tenant_key: Optional[str]
    ) -> ReadOperation:
        raise NotImplementedError("abstract class")


class WriteApis:
    async def sync_user(self, user: UserInput) -> WriteOperation:
        raise NotImplementedError("abstract class")

    async def delete_user(self, user_key: str) -> WriteOperation:
        raise NotImplementedError("abstract class")

    async def create_tenant(self, tenant: Tenant) -> WriteOperation:
        raise NotImplementedError("abstract class")

    async def update_tenant(self, tenant: Tenant) -> WriteOperation:
        raise NotImplementedError("abstract class")

    async def delete_tenant(self, tenant_key: str) -> WriteOperation:
        raise NotImplementedError("abstract class")

    async def assign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> WriteOperation:
        raise NotImplementedError("abstract class")

    async def unassign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> WriteOperation:
        raise NotImplementedError("abstract class")


class PermitApi(ReadApis, WriteApis):
    pass


class MutationsClient(PermitApi):
    def __init__(self, config: PermitConfig):
        self._config = config
        self._logger = logger.bind(name="permit.mutations.client")
        self._headers = {
            "Authorization": f"Bearer {self._config.token}",
            "Content-Type": "application/json",
        }
        self._base_url = self._config.pdp

    # read api ----------------------------------------------------------------
    async def get_user(self, user_key: str) -> ReadOperation:
        async def _get_user() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.get_user({user_key})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.get(
                        f"{self._base_url}/cloud/users/{user_key}",
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to get user with key: {user_key}, got error: {err}"
                    )
                    raise

        return ReadOperation(_get_user)

    async def get_role(self, role_key: str) -> ReadOperation:
        async def _get_role() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.get_role({role_key})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.get(
                        f"{self._base_url}/cloud/roles/{role_key}",
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to get role with id: {role_key}, got error: {err}"
                    )
                    raise

        return ReadOperation(_get_role)

    async def get_tenant(self, tenant_key: str) -> ReadOperation:
        async def _get_tenant() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.get_tenant({tenant_key})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.get(
                        f"{self._base_url}/cloud/tenants/{tenant_key}",
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to get tenant with id: {tenant_key}, got error: {err}"
                    )
                    raise

        return ReadOperation(_get_tenant)

    async def get_assigned_roles(
        self, user_key: str, tenant_key: Optional[str]
    ) -> ReadOperation:
        async def _get_assigned_roles() -> dict:
            if self._config.debug_mode:
                self._logger.info(
                    f"permit.api.get_assigned_roles(user={user_key}, tenant={tenant_key})"
                )

            async with aiohttp.ClientSession(headers=self._headers) as session:
                url = f"{self._base_url}/cloud/role_assignments?user={user_key}"
                if tenant_key is not None:
                    url += f"&tenant={tenant_key}"
                try:
                    async with session.get(url) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"could not get user roles for user {user_key}, got error: {err}"
                    )
                    raise

        return ReadOperation(_get_assigned_roles)

    # write api ---------------------------------------------------------------
    async def sync_user(self, user: UserInput) -> WriteOperation:
        async def _sync_user() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.sync_user({repr(user.dict())})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.put(
                        f"{self._base_url}/cloud/users",
                        data=json.dumps(user.dict(exclude_none=True)),
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to sync user with key: {user.key}, got error: {err}"
                    )
                    raise

        return WriteOperation(_sync_user)

    async def delete_user(self, user_key: str) -> WriteOperation:
        async def _delete_user() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.delete_user({user_key})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.delete(
                        f"{self._base_url}/cloud/users/{user_key}",
                    ) as response:
                        return dict(status=response.status)
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to delete user with key: {user_key}, got error: {err}"
                    )
                    raise

        return WriteOperation(_delete_user)

    async def create_tenant(self, tenant: Tenant) -> WriteOperation:
        async def _create_tenant() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.create_tenant({repr(tenant.dict())})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                data = dict(externalId=tenant.key, name=tenant.name)
                if tenant.description is not None:
                    data["description"] = tenant.description

                try:
                    async with session.put(
                        f"{self._base_url}/cloud/tenants",
                        data=json.dumps(data),
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to create tenant with key: {tenant.key}, got error: {err}"
                    )
                    raise

        return WriteOperation(_create_tenant)

    async def update_tenant(self, tenant: Tenant) -> WriteOperation:
        async def _update_tenant() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.update_tenant({repr(tenant.dict())})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                data = dict(name=tenant.name)
                if tenant.description is not None:
                    data["description"] = tenant.description

                try:
                    async with session.patch(
                        f"{self._base_url}/cloud/tenants/{tenant.key}",
                        data=json.dumps(data),
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to update tenant with key: {tenant.key}, got error: {err}"
                    )
                    raise

        return WriteOperation(_update_tenant)

    async def delete_tenant(self, tenant_key: str) -> WriteOperation:
        async def _delete_tenant() -> dict:
            if self._config.debug_mode:
                self._logger.info(f"permit.api.delete_tenant({tenant_key})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.delete(
                        f"{self._base_url}/cloud/tenants/{tenant_key}",
                    ) as response:
                        return dict(status=response.status)
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"tried to delete tenant with key: {tenant_key}, got error: {err}"
                    )
                    raise

        return WriteOperation(_delete_tenant)

    async def assign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> WriteOperation:
        async def _assign_role() -> dict:
            data = dict(role=role_key, user=user_key, scope=tenant_key)
            if self._config.debug_mode:
                self._logger.info(f"permit.api.assign_role({repr(data)})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.post(
                        f"{self._base_url}/cloud/role_assignments",
                        data=json.dumps(data),
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"could not assign role {role_key} to {user_key} in tenant {tenant_key}, got error: {err}"
                    )
                    raise

        return WriteOperation(_assign_role)

    async def unassign_role(
        self, user_key: str, role_key: str, tenant_key: str
    ) -> WriteOperation:
        async def _unassign_role() -> dict:
            data = dict(role=role_key, user=user_key, scope=tenant_key)
            if self._config.debug_mode:
                self._logger.info(f"permit.api.unassign_role({repr(data)})")

            async with aiohttp.ClientSession(headers=self._headers) as session:
                try:
                    async with session.delete(
                        f"{self._base_url}/cloud/role_assignments?role={role_key}&user={user_key}&scope={tenant_key}",
                    ) as response:
                        return await response.json()
                except aiohttp.ClientError as err:
                    self._logger.error(
                        f"could not unassign role {role_key} of {user_key} in tenant {tenant_key}, got error: {err}"
                    )
                    raise

        return WriteOperation(_unassign_role)
