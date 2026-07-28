"""Async API client for MSKMiner firmware."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import uuid
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
            # unsafe=True allows storing cookies from IP-address hosts.
            # By default aiohttp rejects such cookies per RFC, but miners
            # are accessed by IP so the session cookie would be silently
            # dropped and every request after login returns 401.
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
            await self._login()
        return self._session

    async def _login(self) -> None:
        # Build multipart/form-data body manually — exact replica of:
        #   requests.post(url, files={"username": (None, u), "password": (None, p)})
        # aiohttp's high-level helpers add Content-Type per part which some
        # firmware versions reject, so we hand-craft the raw bytes instead.
        boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="username"\r\n'
            f"\r\n"
            f"{self.username}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="password"\r\n'
            f"\r\n"
            f"{self.password}\r\n"
            f"--{boundary}--\r\n"
        ).encode()

        try:
            async with self._session.post(
                f"{self.base_url}/admin/login",
                auth=aiohttp.BasicAuth(self.username, self.password),
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                timeout=LOGIN_TIMEOUT,
            ) as resp:
                _LOGGER.debug("Login %s → HTTP %s", self.host, resp.status)
                if resp.status in (401, 403):
                    raise InvalidAuth(f"Bad credentials for {self.host}")
                resp.raise_for_status()
        except InvalidAuth:
            raise
        except aiohttp.ClientError as err:
            raise CannotConnect(f"Login failed for {self.host}: {err}") from err

    async def _get(self, path: str) -> Any:
        session = await self._ensure_session()
        for url in (f"{self.api_url}/{path}", f"{self.base_url}/{path}"):
            try:
                async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                    if resp.status == 404:
                        continue
                    if resp.status in (401, 403):
                        await self._login()
                        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp2:
                            resp2.raise_for_status()
                            return await resp2.json(content_type=None)
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
            except (InvalidAuth, CannotConnect):
                raise
            except aiohttp.ClientResponseError as err:
                if err.status == 404:
                    continue
                raise CannotConnect(f"{self.host} request failed: {err}") from err
            except aiohttp.ClientError as err:
                raise CannotConnect(f"{self.host} request failed: {err}") from err
        raise CannotConnect(f"{self.host}: endpoint not found: {path}")

    async def _post(self, path: str, json: dict | None = None) -> Any:
        session = await self._ensure_session()
        # Try /api/<path> first, fall back to /<path> if 404
        for url in (f"{self.api_url}/{path}", f"{self.base_url}/{path}"):
            try:
                async with session.post(url, json=json, timeout=REQUEST_TIMEOUT) as resp:
                    if resp.status == 404:
                        continue
                    resp.raise_for_status()
                    try:
                        return await resp.json(content_type=None)
                    except Exception:
                        return {}
            except aiohttp.ClientResponseError as err:
                if err.status == 404:
                    continue
                raise CannotConnect(f"{self.host} request failed: {err}") from err
            except aiohttp.ClientError as err:
                raise CannotConnect(f"{self.host} request failed: {err}") from err
        raise CannotConnect(f"{self.host}: endpoint not found: {path}")

    async def _delete(self, path: str) -> Any:
        session = await self._ensure_session()
        for url in (f"{self.api_url}/{path}", f"{self.base_url}/{path}"):
            try:
                async with session.delete(url, timeout=REQUEST_TIMEOUT) as resp:
                    if resp.status == 404:
                        continue
                    resp.raise_for_status()
                    try:
                        return await resp.json(content_type=None)
                    except Exception:
                        return {}
            except aiohttp.ClientResponseError as err:
                if err.status == 404:
                    continue
                raise CannotConnect(f"{self.host} request failed: {err}") from err
            except aiohttp.ClientError as err:
                raise CannotConnect(f"{self.host} request failed: {err}") from err
        raise CannotConnect(f"{self.host}: endpoint not found: {path}")

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    async def get_info(self) -> dict[str, Any]:
        """Fetch all data via /api/info_app."""
        return await self._get("info_app")

    async def get_pools(self) -> dict[str, Any]:
        return await self._get("pools")

    async def get_pools_status(self) -> dict[str, Any]:
        return await self._get("pools/status")

    async def get_power_limit(self) -> dict[str, Any]:
        return await self._get("power_limit")

    async def get_summary(self) -> dict[str, Any]:
        return await self._get("summary")

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def restart_miner(self) -> None:
        """Restart mining process (soft restart)."""
        await self._post("restart")

    async def reboot_device(self) -> None:
        """Reboot the physical device."""
        await self._post("reboot")

    async def suspend_mining(self) -> None:
        await self._post("suspend")

    async def resume_mining(self) -> None:
        await self._post("resume")

    async def set_led(self, enabled: bool) -> None:
        await self._post("led", json={"enabled": enabled})

    async def clear_errors(self) -> None:
        await self._delete("clear_errors")

    async def set_cool_mode(self, mode: str) -> None:
        await self._post("cool_mode", json={"mode": mode})

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
        if data is not None:  # {} or null would fail "if data:" but still means connected
            _LOGGER.warning("MSKMiner found at %s", ip)
            return ip
        _LOGGER.warning("%s: connected but got empty response", ip)
    except asyncio.TimeoutError:
        _LOGGER.debug("%s: timeout", ip)
    except InvalidAuth:
        _LOGGER.warning("%s: connected but credentials rejected", ip)
    except CannotConnect as err:
        _LOGGER.warning("%s: cannot connect — %s", ip, err)
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
    _LOGGER.warning(
        "MSKMiner scan of %s complete: found %d device(s): %s",
        ip_range, len(found), found,
    )
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
