"""Async API client for MSKMiner firmware."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
LOGIN_TIMEOUT = aiohttp.ClientTimeout(total=10)


class CannotConnect(Exception):
    """Raised when connection to miner fails."""


class InvalidAuth(Exception):
    """Raised when login credentials are rejected."""


class MSKMinerAPI:
    """Async client for MSKMiner API. Maintains a login session per miner."""

    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host
        self.base_url = f"http://{host}"
        self.api_url = f"{self.base_url}/api"
        self.username = username
        self.password = password
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Session & auth
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            await self._login()
        return self._session

    async def _login(self) -> None:
        basic_auth = aiohttp.BasicAuth(self.username, self.password)
        last_err: Exception | None = None

        # Try multipart first (matches requests files={}), then urlencoded fallback.
        for payload in (self._multipart_payload(), {"username": self.username, "password": self.password}):
            is_form = isinstance(payload, dict)
            kwargs = {"data": payload} if is_form else {"data": payload}
            try:
                async with self._session.post(
                    f"{self.base_url}/admin/login",
                    auth=basic_auth,
                    timeout=LOGIN_TIMEOUT,
                    **kwargs,
                ) as resp:
                    _LOGGER.debug(
                        "Login attempt to %s → HTTP %s", self.host, resp.status
                    )
                    if resp.status in (401, 403):
                        raise InvalidAuth(f"Bad credentials for {self.host}")
                    if resp.ok:
                        return
                    last_err = Exception(f"HTTP {resp.status}")
            except InvalidAuth:
                raise
            except aiohttp.ClientError as err:
                _LOGGER.debug("Login network error %s: %s", self.host, err)
                last_err = err

        raise CannotConnect(f"Login failed for {self.host}: {last_err}") from last_err

    def _multipart_payload(self) -> aiohttp.FormData:
        form = aiohttp.FormData()
        form.add_field("username", self.username, content_type="text/plain")
        form.add_field("password", self.password, content_type="text/plain")
        return form

    async def _get(self, path: str) -> Any:
        session = await self._ensure_session()
        try:
            async with session.get(
                f"{self.api_url}/{path}", timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    # Session expired — re-login once
                    await self._login()
                    async with session.get(
                        f"{self.api_url}/{path}", timeout=REQUEST_TIMEOUT
                    ) as resp2:
                        resp2.raise_for_status()
                        return await resp2.json(content_type=None)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (InvalidAuth, CannotConnect):
            raise
        except aiohttp.ClientError as err:
            raise CannotConnect(f"{self.host} request failed: {err}") from err

    async def _post(self, path: str, json: dict | None = None) -> Any:
        session = await self._ensure_session()
        try:
            async with session.post(
                f"{self.api_url}/{path}", json=json, timeout=REQUEST_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                try:
                    return await resp.json(content_type=None)
                except Exception:
                    return {}
        except aiohttp.ClientError as err:
            raise CannotConnect(f"{self.host} request failed: {err}") from err

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    async def get_info(self) -> dict[str, Any]:
        """Fetch all data via /api/info_app."""
        return await self._get("info_app")

    async def get_status(self) -> dict[str, Any]:
        return await self._get("status")

    async def get_power(self) -> dict[str, Any]:
        return await self._get("power")

    async def get_uptime(self) -> dict[str, Any]:
        return await self._get("uptime")

    async def get_pools(self) -> dict[str, Any]:
        return await self._get("pools")

    async def get_miner_status(self) -> dict[str, Any]:
        return await self._get("miner_status")

    async def is_stopped(self) -> bool:
        data = await self._get("miner_stopped")
        return bool(data.get("stopped", False))

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def restart_miner(self) -> None:
        """Restart mining process (soft restart)."""
        await self._post("miner_restart")

    async def reboot_device(self) -> None:
        """Reboot the physical device."""
        await self._post("reboot")

    async def pause_mining(self) -> None:
        await self._post("miner_pause")

    async def resume_mining(self) -> None:
        await self._post("miner_resume")

    async def blink_start(self) -> None:
        await self._post("blink/start")

    async def blink_stop(self) -> None:
        await self._post("blink/stop")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


# ------------------------------------------------------------------
# Network discovery
# ------------------------------------------------------------------

async def _probe_host(
    ip: str, username: str, password: str, timeout: int
) -> str | None:
    """Return IP if MSKMiner is reachable, None otherwise."""
    api = MSKMinerAPI(ip, username, password)
    try:
        data = await asyncio.wait_for(api.get_info(), timeout=timeout)
        if data:
            _LOGGER.debug("MSKMiner found at %s", ip)
            return ip
    except asyncio.TimeoutError:
        _LOGGER.debug("%s: timeout", ip)
    except InvalidAuth:
        _LOGGER.warning("%s: connected but credentials rejected", ip)
    except CannotConnect as err:
        _LOGGER.debug("%s: cannot connect — %s", ip, err)
    except Exception as err:
        _LOGGER.warning("%s: unexpected error — %s: %s", ip, type(err).__name__, err)
    finally:
        await api.close()
    return None


async def discover_miners(
    ip_range: str,
    username: str,
    password: str,
    connect_timeout: int = 5,
    concurrency: int = 30,
) -> list[str]:
    """Scan an IP range and return IPs of reachable MSKMiner devices.

    Accepts: CIDR (192.168.1.0/24), range (192.168.1.1-254 or
    192.168.1.1-192.168.1.254), or single IP.
    """
    hosts = _parse_ip_range(ip_range)
    if not hosts:
        return []

    semaphore = asyncio.Semaphore(concurrency)
    found: list[str] = []

    async def check(ip: str) -> None:
        async with semaphore:
            result = await _probe_host(ip, username, password, connect_timeout + 2)
            if result:
                found.append(result)

    await asyncio.gather(*[check(ip) for ip in hosts], return_exceptions=True)
    return sorted(found, key=lambda x: tuple(int(o) for o in x.split(".")))


def _parse_ip_range(ip_range: str) -> list[str]:
    ip_range = ip_range.strip()
    try:
        if "/" in ip_range:
            network = ipaddress.ip_network(ip_range, strict=False)
            return [str(ip) for ip in network.hosts()]

        if "-" in ip_range:
            start_str, end_str = ip_range.split("-", 1)
            start_ip = ipaddress.ip_address(start_str.strip())
            end_str = end_str.strip()
            if "." in end_str:
                end_ip = ipaddress.ip_address(end_str)
            else:
                # Only last octet: 192.168.1.1-254
                base = str(start_ip).rsplit(".", 1)[0]
                end_ip = ipaddress.ip_address(f"{base}.{end_str}")
            hosts = []
            current = int(start_ip)
            end = int(end_ip)
            while current <= end:
                hosts.append(str(ipaddress.ip_address(current)))
                current += 1
            return hosts

        # Single IP
        ipaddress.ip_address(ip_range)
        return [ip_range]
    except ValueError:
        _LOGGER.error("Cannot parse IP range: %s", ip_range)
        return []
