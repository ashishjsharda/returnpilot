"""
Storage abstraction for ReturnPilot's memory: purchases + learned preferences.

Two backends behind one interface:
  - LocalSQLiteStore  -> zero AWS setup, used by default (RETURNPILOT_STORAGE=local)
  - DynamoDBStore     -> real AWS, used when RETURNPILOT_STORAGE=dynamodb and
                          credentials are available (auto-creates the table on
                          first use)

This is the piece the architecture diagram labels "DynamoDB / Purchase
Memory" — swapping backends is a one-line env var change, no code change.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from src import config
from src.models import Purchase


class BaseStore:
    def save_purchase(self, purchase: Purchase) -> None:
        raise NotImplementedError

    def get_purchase(self, purchase_id: str) -> Optional[Purchase]:
        raise NotImplementedError

    def list_purchases(self, status: Optional[str] = None) -> list[Purchase]:
        raise NotImplementedError

    def update_purchase(self, purchase_id: str, **fields) -> Optional[Purchase]:
        raise NotImplementedError

    def set_preference(self, merchant: str, key: str, value: str) -> None:
        raise NotImplementedError

    def get_preference(self, merchant: str, key: str) -> Optional[str]:
        raise NotImplementedError

    def list_preferences(self) -> list[dict]:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError


class LocalSQLiteStore(BaseStore):
    def __init__(self, db_path: str = config.LOCAL_DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS purchases (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS preferences (
                    merchant TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (merchant, key)
                )
                """
            )

    def save_purchase(self, purchase: Purchase) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO purchases (id, data) VALUES (?, ?)",
                (purchase.id, json.dumps(purchase.to_dict())),
            )

    def get_purchase(self, purchase_id: str) -> Optional[Purchase]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM purchases WHERE id = ?", (purchase_id,)
            ).fetchone()
            return Purchase.from_dict(json.loads(row["data"])) if row else None

    def list_purchases(self, status: Optional[str] = None) -> list[Purchase]:
        with self._conn() as conn:
            rows = conn.execute("SELECT data FROM purchases").fetchall()
        purchases = [Purchase.from_dict(json.loads(r["data"])) for r in rows]
        if status:
            purchases = [p for p in purchases if p.status == status]
        return sorted(purchases, key=lambda p: p.return_deadline)

    def update_purchase(self, purchase_id: str, **fields) -> Optional[Purchase]:
        purchase = self.get_purchase(purchase_id)
        if not purchase:
            return None
        for k, v in fields.items():
            setattr(purchase, k, v)
        self.save_purchase(purchase)
        return purchase

    def set_preference(self, merchant: str, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preferences (merchant, key, value) VALUES (?, ?, ?)",
                (merchant, key, value),
            )

    def get_preference(self, merchant: str, key: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM preferences WHERE merchant = ? AND key = ?",
                (merchant, key),
            ).fetchone()
            return row["value"] if row else None

    def list_preferences(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT merchant, key, value FROM preferences").fetchall()
        return [dict(r) for r in rows]

    def reset(self) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM purchases")
            conn.execute("DELETE FROM preferences")


class DynamoDBStore(BaseStore):
    """
    Real AWS backend. Auto-creates the table (on-demand billing) on first use
    so there's no manual console step before the demo.
    """

    def __init__(self, table_name: str = config.DYNAMODB_TABLE, region: str = config.AWS_REGION):
        import boto3

        self.region = region
        self.table_name = table_name
        self._resource = boto3.resource("dynamodb", region_name=region)
        self._table = self._ensure_table()
        self._pref_table = self._ensure_pref_table()

    def _ensure_table(self):
        existing = [t.name for t in self._resource.tables.all()]
        if self.table_name not in existing:
            table = self._resource.create_table(
                TableName=self.table_name,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            table.wait_until_exists()
            return table
        return self._resource.Table(self.table_name)

    def _ensure_pref_table(self):
        pref_table_name = f"{self.table_name}Preferences"
        existing = [t.name for t in self._resource.tables.all()]
        if pref_table_name not in existing:
            table = self._resource.create_table(
                TableName=pref_table_name,
                KeySchema=[
                    {"AttributeName": "merchant", "KeyType": "HASH"},
                    {"AttributeName": "key", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "merchant", "AttributeType": "S"},
                    {"AttributeName": "key", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            table.wait_until_exists()
            return table
        return self._resource.Table(pref_table_name)

    def save_purchase(self, purchase: Purchase) -> None:
        self._table.put_item(Item=purchase.to_dict())

    def get_purchase(self, purchase_id: str) -> Optional[Purchase]:
        resp = self._table.get_item(Key={"id": purchase_id})
        item = resp.get("Item")
        return Purchase.from_dict(item) if item else None

    def list_purchases(self, status: Optional[str] = None) -> list[Purchase]:
        resp = self._table.scan()
        purchases = [Purchase.from_dict(i) for i in resp.get("Items", [])]
        if status:
            purchases = [p for p in purchases if p.status == status]
        return sorted(purchases, key=lambda p: p.return_deadline)

    def update_purchase(self, purchase_id: str, **fields) -> Optional[Purchase]:
        purchase = self.get_purchase(purchase_id)
        if not purchase:
            return None
        for k, v in fields.items():
            setattr(purchase, k, v)
        self.save_purchase(purchase)
        return purchase

    def set_preference(self, merchant: str, key: str, value: str) -> None:
        self._pref_table.put_item(Item={"merchant": merchant, "key": key, "value": value})

    def get_preference(self, merchant: str, key: str) -> Optional[str]:
        resp = self._pref_table.get_item(Key={"merchant": merchant, "key": key})
        item = resp.get("Item")
        return item["value"] if item else None

    def list_preferences(self) -> list[dict]:
        resp = self._pref_table.scan()
        return resp.get("Items", [])

    def reset(self) -> None:
        for p in self.list_purchases():
            self._table.delete_item(Key={"id": p.id})
        for pref in self.list_preferences():
            self._pref_table.delete_item(Key={"merchant": pref["merchant"], "key": pref["key"]})


_store_instance: Optional[BaseStore] = None


def get_store() -> BaseStore:
    """Factory: returns the configured backend, falling back to local SQLite
    if DynamoDB was requested but isn't actually reachable (missing creds,
    no network, etc.) so a demo never hard-fails on AWS plumbing."""
    global _store_instance
    if _store_instance is not None:
        return _store_instance

    if config.STORAGE_BACKEND == "dynamodb":
        try:
            _store_instance = DynamoDBStore()
            return _store_instance
        except Exception as exc:  # noqa: BLE001
            print(f"[memory] DynamoDB unavailable ({exc}); falling back to local SQLite.")

    _store_instance = LocalSQLiteStore()
    return _store_instance
