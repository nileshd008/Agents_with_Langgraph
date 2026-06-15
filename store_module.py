import langgraph
from langgraph.store.memory import InMemoryStore
import sqlite3
from langgraph.store.sqlite import SqliteStore
import asyncio
import contextlib
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

checkpointer = None
    

async def saver():
    global checkpointer
    conn = await aiosqlite.connect("./artifacts_vault.db")
    checkpointer = AsyncSqliteSaver(conn)
    return checkpointer


@contextlib.asynccontextmanager
async def get_artifact_store():
    async with AsyncSqliteStore.from_conn_string("./artifacts_vault.db") as store:
        await store.setup()
        yield store

