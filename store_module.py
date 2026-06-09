import langgraph
from langgraph.store.memory import InMemoryStore
import sqlite3
from langgraph.store.sqlite import SqliteStore

import contextlib
from langgraph.store.sqlite import AsyncSqliteStore, AsyncSqliteSaver

@contextlib.asynccontextmanager
async def get_artifact_store():
    async with AsyncSqliteStore.from_conn_string("./artifacts_vault.db") as store:
        await store.setup()
        yield store