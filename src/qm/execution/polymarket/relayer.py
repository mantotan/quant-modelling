"""Polymarket Relayer API Client — gasless on-chain claims.

Ported from polymarket-copy-trade/src/lib/relayer-client.ts.
Supports redeeming winning positions without paying gas (MATIC).

For POLY_PROXY wallets: wraps CTF.redeemPositions in ProxyWalletFactory.proxy().
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import aiohttp
from eth_abi import encode
from eth_utils import keccak

logger = logging.getLogger(__name__)

# Contract addresses (Polygon mainnet)
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
PROXY_FACTORY_ADDRESS = "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052"

# Function selectors
# redeemPositions(address,bytes32,bytes32,uint256[])
REDEEM_SELECTOR = keccak(text="redeemPositions(address,bytes32,bytes32,uint256[])")[:4]
# proxy((uint8,address,uint256,bytes)[])
PROXY_SELECTOR = keccak(text="proxy((uint8,address,uint256,bytes)[])")[:4]

TERMINAL_STATES = {"STATE_CONFIRMED", "STATE_FAILED", "STATE_INVALID"}


class RelayerClient:
    """Gas-free transaction relay via Polymarket Relayer API.

    Usage:
        relayer = RelayerClient.from_env()
        tx_id = await relayer.redeem_positions(condition_id, [1])  # UP won
        result = await relayer.wait_for_relay(tx_id)
    """

    def __init__(
        self,
        api_key: str,
        api_key_address: str,
        private_key: str,
        relayer_url: str = "https://relayer-v2.polymarket.com",
        signature_type: int = 1,  # 0=EOA, 1=POLY_PROXY
    ) -> None:
        self._api_key = api_key
        self._api_key_address = api_key_address
        self._private_key = private_key
        self._relayer_url = relayer_url.rstrip("/")
        self._signature_type = signature_type
        self._session: aiohttp.ClientSession | None = None

    @classmethod
    def from_env(cls) -> RelayerClient:
        """Create from environment variables."""
        return cls(
            api_key=os.environ.get("POLYMARKET_RELAYER_API_KEY", ""),
            api_key_address=os.environ.get("POLYMARKET_RELAYER_API_KEY_ADDRESS", ""),
            private_key=os.environ.get("POLYMARKET_PRIVATE_KEY", ""),
            relayer_url=os.environ.get(
                "POLYMARKET_RELAYER_URL",
                "https://relayer-v2.polymarket.com",
            ),
            signature_type=int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "1")),
        )

    @property
    def is_ready(self) -> bool:
        return bool(self._api_key and self._private_key)

    async def redeem_positions(
        self,
        condition_id: str,
        index_sets: list[int],
    ) -> str | None:
        """Submit gasless claim for resolved positions.

        Args:
            condition_id: Market condition ID (hex string).
            index_sets: [1] for UP won, [2] for DN won, [1,2] for matched pairs.

        Returns:
            Transaction ID from relayer, or None on failure.
        """
        if not self.is_ready:
            logger.warning("Relayer not configured — skipping claim")
            return None

        try:
            # Encode CTF.redeemPositions(USDC, parentCollectionId=0x0, conditionId, indexSets)
            parent_collection = bytes(32)  # bytes32(0)
            condition_bytes = bytes.fromhex(condition_id.replace("0x", "").zfill(64))

            redeem_calldata = REDEEM_SELECTOR + encode(
                ["address", "bytes32", "bytes32", "uint256[]"],
                [USDC_ADDRESS, parent_collection, condition_bytes, index_sets],
            )

            if self._signature_type == 0:
                # EOA: direct call to CTF
                tx_to = CTF_ADDRESS
                tx_data = "0x" + redeem_calldata.hex()
            else:
                # POLY_PROXY: wrap in ProxyWalletFactory.proxy()
                # proxy([(typeCode=1, to=CTF, value=0, data=redeemCalldata)])
                proxy_tuple = [(1, CTF_ADDRESS, 0, redeem_calldata)]
                proxy_calldata = PROXY_SELECTOR + encode(
                    ["(uint8,address,uint256,bytes)[]"],
                    [proxy_tuple],
                )
                tx_to = PROXY_FACTORY_ADDRESS
                tx_data = "0x" + proxy_calldata.hex()

            # Get nonce from relayer
            from eth_account import Account

            account = Account.from_key(self._private_key)
            signer_address = account.address

            nonce_resp = await self._fetch(
                "GET", f"/nonce?address={signer_address}&type=PROXY",
            )
            nonce = nonce_resp.get("nonce", 0)

            # Sign the relay message: keccak256(to, value, data, nonce)
            from eth_account.messages import encode_defunct

            message_hash = keccak(encode(
                ["address", "uint256", "bytes", "uint256"],
                [tx_to, 0, bytes.fromhex(tx_data[2:]), nonce],
            ))
            signable = encode_defunct(primitive=message_hash)
            signed = account.sign_message(signable)
            signature = signed.signature.hex()

            # Submit to relayer
            payload = {
                "type": "PROXY",
                "from": signer_address,
                "to": tx_to,
                "data": tx_data,
                "signature": "0x" + signature,
                "metadata": "qm-divergence",
            }

            resp = await self._fetch("POST", "/submit", payload)
            tx_id = resp.get("transactionID", "")

            logger.info(
                "Relayer claim submitted: condition=%s indexSets=%s → txId=%s",
                condition_id[:16], index_sets, tx_id[:16] if tx_id else "none",
            )
            return tx_id

        except Exception as e:
            logger.warning("Relayer claim failed for %s: %s", condition_id[:16], e)
            return None

    async def wait_for_relay(
        self,
        tx_id: str,
        timeout: float = 120.0,
        poll_interval: float = 3.0,
    ) -> dict:
        """Poll relayer until transaction reaches terminal state.

        Returns dict with keys: id, state, transactionHash.
        """
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            try:
                resp = await self._fetch("GET", f"/transaction/{tx_id}")
                tx = resp[0] if isinstance(resp, list) else resp

                state = tx.get("state", "STATE_NEW")
                if state in TERMINAL_STATES:
                    tx_hash = tx.get("transactionHash", "")
                    logger.info(
                        "Relayer TX %s: %s (hash=%s)",
                        tx_id[:16], state, tx_hash[:16] if tx_hash else "none",
                    )
                    return {"id": tx_id, "state": state, "transactionHash": tx_hash}
            except Exception as e:
                logger.debug("Relayer poll failed: %s", e)

            await asyncio.sleep(poll_interval)

        logger.warning("Relayer TX %s timed out after %.0fs", tx_id[:16], timeout)
        return {"id": tx_id, "state": "STATE_TIMEOUT", "transactionHash": ""}

    async def _fetch(self, method: str, path: str, body: dict | None = None) -> dict:
        """Make authenticated request to relayer API."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

        url = f"{self._relayer_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "RELAYER_API_KEY": self._api_key,
            "RELAYER_API_KEY_ADDRESS": self._api_key_address,
        }

        async with self._session.request(
            method, url, headers=headers,
            json=body if body else None,
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                msg = f"Relayer API {method} {path}: {resp.status} {text[:200]}"
                raise RuntimeError(msg)
            return await resp.json()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
