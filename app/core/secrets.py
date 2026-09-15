import os

from pydantic import BaseModel


class VaultConfig(BaseModel):
    url: str = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
    token: str = os.getenv("VAULT_TOKEN", "")
    mount_point: str = os.getenv("VAULT_MOUNT", "secret")
    enabled: bool = os.getenv("SECRETS_VAULT_ENABLED", "false").lower() == "true"


vault_config = VaultConfig()

_secrets_cache: dict = {}


async def get_secret(path: str, key: str) -> str | None:
    if not vault_config.enabled:
        cache_key = f"{path}/{key}"
        return _secrets_cache.get(cache_key)

    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{vault_config.url}/v1/{vault_config.mount_point}/data/{path}",
                headers={"X-Vault-Token": vault_config.token},
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("data", {})
                return data.get(key)
    except Exception:
        pass
    return None


async def set_secret(path: str, key: str, value: str) -> bool:
    if not vault_config.enabled:
        cache_key = f"{path}/{key}"
        _secrets_cache[cache_key] = value
        return True

    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{vault_config.url}/v1/{vault_config.mount_point}/data/{path}",
                headers={"X-Vault-Token": vault_config.token},
                json={"data": {key: value}},
            )
            return resp.status_code in (200, 204)
    except Exception:
        return False
