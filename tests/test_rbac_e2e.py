import time
from typing import List

import pytest
from loguru import logger
import asyncio

from werkzeug import Response, Request

from permit import Permit, RoleAssignmentRead
from permit.exceptions import PermitApiError, PermitConnectionError

from .utils import handle_api_error
import time
from pytest_httpserver import HTTPServer


def print_break():
    print("\n\n ----------- \n\n")


TEST_TIMEOUT = 1
MOCKED_URL = "http://localhost"
MOCKED_PORT = 9999
def sleeping(request: Request):
    time.sleep(TEST_TIMEOUT+1)
    return Response("OK", status=200)


@pytest.fixture(scope="session")
def httpserver_listen_address():
    return "localhost", MOCKED_PORT


async def test_api_timeout(httpserver: HTTPServer):
    permit = Permit(token="mocked", pdp=f"{MOCKED_URL}:{MOCKED_PORT}", api_url=f"{MOCKED_URL}:{MOCKED_PORT}", api_timeout=TEST_TIMEOUT)
    current_time = time.time()
    httpserver.expect_request("/v2/api-key/scope").respond_with_handler(sleeping)
    with pytest.raises(asyncio.TimeoutError):
        await permit.api.roles.list()
    time_passed = time.time() - current_time
    assert time_passed < 3


async def test_pdp_timeout(httpserver: HTTPServer):
    permit = Permit(token="mocked", pdp=f"{MOCKED_URL}:{MOCKED_PORT}", api_url=f"{MOCKED_URL}:{MOCKED_PORT}", pdp_timeout=TEST_TIMEOUT)
    current_time = time.time()
    httpserver.expect_request("/allowed").respond_with_handler(sleeping)
    with pytest.raises(asyncio.TimeoutError):
        await permit.check("user", "action", {"type": "resource", "tenant": "tenant"})
    time_passed = time.time() - current_time
    assert time_passed < 3

    current_time = time.time()
    httpserver.expect_request("/allowed/bulk").respond_with_handler(sleeping)
    with pytest.raises(asyncio.TimeoutError):
        await permit.bulk_check([{"user": "user", "action": "action", "resource": {"type": "resource", "tenant": "tenant"}}])
    time_passed = time.time() - current_time
    assert time_passed < 3

async def test_permission_check_e2e(permit: Permit):
    logger.info("initial setup of objects")
    try:
        document = await permit.api.resources.create(
            {
                "key": "document",
                "name": "Document",
                "urn": "prn:gdrive:document",
                "description": "google drive document",
                "actions": {
                    "create": {},
                    "read": {},
                    "update": {},
                    "delete": {},
                },
                "attributes": {
                    "private": {
                        "type": "bool",
                        "description": "whether the document is private",
                    },
                },
            }
        )

        # verify create output
        assert document is not None
        assert document.id is not None
        assert document.key == "document"
        assert document.name == "Document"
        assert document.description == "google drive document"
        assert document.urn == "prn:gdrive:document"
        assert len(document.actions or {}) == 4
        assert (document.actions or {}).get("create") is not None
        assert (document.actions or {}).get("read") is not None
        assert (document.actions or {}).get("update") is not None
        assert (document.actions or {}).get("delete") is not None

        # verify list output
        resources = await permit.api.resources.list()
        assert len(resources) == 1
        assert resources[0].id == document.id
        assert resources[0].key == document.key
        assert resources[0].name == document.name
        assert resources[0].description == document.description
        assert resources[0].urn == document.urn

        # create admin role
        admin = await permit.api.roles.create(
            {
                "key": "admin",
                "name": "Admin",
                "description": "an admin role",
                "permissions": ["document:create", "document:read"],
            }
        )

        assert admin is not None
        assert admin.key == "admin"
        assert admin.name == "Admin"
        assert admin.description == "an admin role"
        assert admin.permissions is not None
        assert "document:create" in admin.permissions
        assert "document:read" in admin.permissions

        # create viewer role
        viewer = await permit.api.roles.create(
            {
                "key": "viewer",
                "name": "Viewer",
                "description": "an viewer role",
            }
        )

        assert viewer is not None
        assert viewer.key == "viewer"
        assert viewer.name == "Viewer"
        assert viewer.description == "an viewer role"
        assert viewer.permissions is not None
        assert len(viewer.permissions) == 0

        # assign permissions to roles
        assigned_viewer = await permit.api.roles.assign_permissions(
            "viewer", ["document:read"]
        )

        assert assigned_viewer.key == "viewer"
        assert len(assigned_viewer.permissions) == 1
        assert "document:read" in assigned_viewer.permissions
        assert "document:create" not in assigned_viewer.permissions

        # create a tenant
        tenant = await permit.api.tenants.create(
            {
                "key": "tesla",
                "name": "Tesla Inc",
                "description": "The car company",
            }
        )

        assert tenant.key == "tesla"
        assert tenant.name == "Tesla Inc"
        assert tenant.description == "The car company"
        assert tenant.attributes is None or len(tenant.attributes) == 0

        # create a user
        user = await permit.api.users.sync(
            {
                "key": "auth0|elon",
                "email": "elonmusk@tesla.com",
                "first_name": "Elon",
                "last_name": "Musk",
                "attributes": {
                    "age": 50,
                    "favoriteColor": "red",
                },
            }
        )

        assert user.key == "auth0|elon"
        assert user.email == "elonmusk@tesla.com"
        assert user.first_name == "Elon"
        assert user.last_name == "Musk"
        assert len(user.attributes or {}) == 2
        assert user.attributes["age"] == 50
        assert user.attributes["favoriteColor"] == "red"

        # assign role to user in tenant
        ra = await permit.api.users.assign_role(
            {
                "user": "auth0|elon",
                "role": "viewer",
                "tenant": "tesla",
            }
        )

        assert ra.user_id == user.id
        assert ra.role_id == viewer.id
        assert ra.tenant_id == tenant.id
        assert ra.user == user.email or ra.user == user.key
        assert ra.role == viewer.key
        assert ra.tenant == tenant.key

        logger.info(
            "sleeping 2 seconds before permit.check() to make sure all writes propagated from cloud to PDP"
        )
        time.sleep(2)

        # positive permission check (will be True because elon is a viewer, and a viewer can read a document)
        logger.info("testing positive permission check")
        resource_attributes = {"secret": True}
        assert await permit.check(
            "auth0|elon",
            "read",
            {"type": "document", "tenant": "tesla", "attributes": resource_attributes},
        )

        print_break()

        logger.info("testing positive permission check with complete user object")
        assert await permit.check(
            user.dict(), "read", {"type": document.key, "tenant": tenant.key}
        )

        print_break()

        # negative permission check (will be False because a viewer cannot create a document)
        logger.info("testing negative permission check")
        assert (
            await permit.check(
                user.key, "create", {"type": document.key, "tenant": tenant.key}
            )
        ) == False

        print_break()

        logger.info("testing bulk permission check")
        assert (
            await permit.bulk_check(
                [
                    {
                        "user": "auth0|elon",
                        "action": "read",
                        "resource": {
                            "type": "document",
                            "tenant": "tesla",
                            "attributes": resource_attributes,
                        },
                    },
                    {
                        "user": user.dict(),
                        "action": "read",
                        "resource": {"type": document.key, "tenant": tenant.key},
                    },
                    {
                        "user": user.key,
                        "action": "create",
                        "resource": {"type": document.key, "tenant": tenant.key},
                    },
                ],
                {},
            )
        ) == [True, True, False]

        print_break()

        logger.info("changing the user roles")

        # change the user role - assign admin role
        await permit.api.users.assign_role(
            {
                "user": user.key,
                "role": admin.key,
                "tenant": tenant.key,
            }
        )
        # change the user role - remove viewer role
        await permit.api.users.unassign_role(
            {
                "user": user.key,
                "role": viewer.key,
                "tenant": tenant.key,
            }
        )

        # list user roles in all tenants
        assigned_roles: List[
            RoleAssignmentRead
        ] = await permit.api.users.get_assigned_roles(user=user.key)

        assert len(assigned_roles) == 1
        assert assigned_roles[0].user_id == user.id
        assert assigned_roles[0].role_id == admin.id
        assert assigned_roles[0].tenant_id == tenant.id

        logger.info(
            "sleeping 2 seconds before permit.check() to make sure all writes propagated from cloud to PDP"
        )
        time.sleep(2)

        # run the same negative permission check again, this time it's True
        logger.info(
            "testing previously negative permission check, should now be positive"
        )
        assert await permit.check(
            user.dict(), "create", {"type": document.key, "tenant": tenant.key}
        )

        print_break()

    except PermitApiError as error:
        handle_api_error(error, "Got API Error")
    except PermitConnectionError as error:
        raise
    except Exception as error:
        logger.error(f"Got error: {error}")
        pytest.fail(f"Got error: {error}")
    finally:
        # cleanup
        try:
            await permit.api.resources.delete("document")
            await permit.api.roles.delete("admin")
            await permit.api.roles.delete("viewer")
            await permit.api.tenants.delete("tesla")
            await permit.api.users.delete("auth0|elon")
            assert len(await permit.api.resources.list()) == 0
            assert len(await permit.api.roles.list()) == 0
            assert len(await permit.api.tenants.list()) == 1  # the default tenant
            assert len((await permit.api.users.list()).data) == 0
        except PermitApiError as error:
            handle_api_error(error, "Got API Error during cleanup")
        except PermitConnectionError as error:
            raise
        except Exception as error:
            logger.error(f"Got error during cleanup: {error}")
            pytest.fail(f"Got error during cleanup: {error}")
