"""Garmin-klient: gjenbruker samme token-cache og pålogging som garmin_mcp
(~/.garminconnect), men er en egen, liten kopi — dette prosjektet er en egen
app, ikke avhengig av garmin_mcp-prosjektet på disk.
"""

import os
import threading

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_STORE = os.path.expanduser("~/.garminconnect")

_CALL_TIMEOUT = 30.0

_ERROR_HINTS = {
    GarminConnectAuthenticationError: "Sesjonen har utløpt. Kjør 'uv run python -m garmin_mcp.auth' i garmin_mcp-prosjektet igjen.",
    GarminConnectTooManyRequestsError: "Garmin rate-limiter deg. Vent noen minutter.",
    GarminConnectConnectionError: "Fikk ikke kontakt med Garmin Connect.",
}


class GarminProxy:
    """Samme mønster som i garmin_mcp: timeout + tydeligere feilmeldinger per kall."""

    def __init__(self, client: Garmin, timeout: float = _CALL_TIMEOUT) -> None:
        self._client = client
        self._timeout = timeout

    def __getattr__(self, name: str):
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            outcome: dict = {}

            def run() -> None:
                try:
                    outcome["value"] = attr(*args, **kwargs)
                except BaseException as exc:  # noqa: BLE001
                    outcome["error"] = exc

            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            worker.join(self._timeout)

            if worker.is_alive():
                raise TimeoutError(f"Garmin-kallet '{name}' svarte ikke innen {self._timeout:g}s.")
            if "error" in outcome:
                error = outcome["error"]
                for exc_type, hint in _ERROR_HINTS.items():
                    if isinstance(error, exc_type):
                        raise type(error)(f"{error} — {hint}") from None
                raise error
            return outcome["value"]

        return wrapped


def get_client() -> GarminProxy:
    client = Garmin()
    client.login(TOKEN_STORE)
    if not client.get_full_name():
        raise GarminConnectAuthenticationError("Sesjonen er ikke autentisert")
    return GarminProxy(client)
