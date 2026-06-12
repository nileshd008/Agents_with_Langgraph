from langchain_mcp_adapters.client import MultiServerMCPClient
import os
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langchain.agents import create_agent
from langgraph.prebuilt import ToolNode
from typing import Annotated, Sequence
from typing_extensions import TypedDict
from operator import add
from langchain_litellm import ChatLiteLLM
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, AnyMessage, ToolMessage, SystemMessage
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
from langgraph.types import Command
from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationError
from typing import Any, Dict, Optional, Literal, List, Callable
import pandas as pd
import uuid
import json
import plotly.io as pio
from pathlib import Path
import hashlib
import copy
from langgraph.prebuilt import InjectedState
from langchain_core.tools import InjectedToolCallId
from langchain_core.tools import tool
from langgraph.store.memory import InMemoryStore
from store_module import get_artifact_store
import asyncio
from langchain.agents.middleware import wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langgraph.prebuilt.tool_node import ToolRuntime
from langchain_core.tools import tool
from langchain.tools import InjectedState
from langgraph.checkpoint.memory import InMemorySaver
from langchain_deepinfra import ChatDeepInfra
from langchain_openai import ChatOpenAI
load_dotenv()


async def get_mcp_client():
    client = MultiServerMCPClient(
        {
            "db_tools": {
                "command": "python",
                "args": ["server.py"],
                "transport": "stdio",
                "env": {
                    "database_name": os.getenv('database_name'),
                    "connection_name": os.getenv('connection_name'),
                    "username": os.getenv('username'),
                    "db_passward": os.getenv('db_passward'),
                    'PYTHONBREAKPOINT': '0'
                },
            }
        },
    )
    return await client.get_tools()


async def save_artifact(artifact: Any, user_id:str, artifact_id: str, type:str = 'artifact'):
    async with get_artifact_store() as store:
        await store.aput((type, user_id), artifact_id, artifact)


@wrap_tool_call
async def store_artifact(request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command]):
    result = await handler(request)
    runtime = request.runtime
    config = runtime.config['configurable']

    if (
        request.tool_call
        and request.tool_call["name"].lower() == "get_sql_table_schema"
    ):
        payload = json.loads(result.content[0]["text"])
        
        if payload['status'].lower() == 'success':
            
            data = json.dumps(data).encode('utf-8')
            artifact_id = hashlib.sha256(data).hexdigest()

            await save_artifact(data, user_id = config['user_id'], artifact_id = artifact_id)


            mime_type = "application/json"
            artifact_type = "json"


            await save_artifact(data = {
                    "schema_version": "1.0",
                    'description': 'Database Table schema',
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "mime_type": mime_type,
                    "source_tool_name": request.tool_call['name'],
                    "source_tool_call_id": request.tool_call['id']
                },
                user_id = config['user_id'],
                artifact_id = artifact_id,
                type = 'manifest'
            )
            

            artifact_ref = {
                'description': 'Database Table schema',
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "mime_type": mime_type,
            }

            payload["data"] = artifact_ref
            result.content[0]["text"] = json.dumps(payload)
            result.artifact = artifact_ref

        return result

    
    if (
        request.tool_call
        and request.tool_call['name'].lower() == 'execute_graph'
    ):
        payload = json.loads(result.content[0]['text'])

        if payload['status'].lower() == 'success': 
            artifact_id = hashlib.sha256(payload['data'].encode('utf-8')).hexdigest()
            html = pio.to_html(pio.from_json(payload['data']), include_plotlyjs=True, full_html=True)
            await save_artifact(html, user_id = config['user_id'], artifact_id = artifact_id)

            mime_type = "text/html"
            artifact_type = "plotly_html"
            
            await save_artifact(
                {   
                    "schema_version": "1.0",
                    'description': 'Plolty visualization Graph',
                    'artifact_id': artifact_id,
                    'artifact_type': artifact_type,
                    'mime_type': mime_type,
                    'uri': f"http://localhost:8000/view/{config['user_id']}/{artifact_id}",
                    "source_tool_name": request.tool_call['name'],
                    "source_tool_call_id": request.tool_call['id']
                },
                user_id = config['user_id'], 
                artifact_id = artifact_id,
                type = 'manifest'
            )

            artifact_ref = {
                'description': 'Plolty visualization Graph',
                'artifact_id': artifact_id,
                'artifact_type': artifact_type,
                'mime_type': mime_type,
                'uri': f"http://localhost:8000/view/{config['user_id']}/{artifact_id}"
            }
            
            payload['data'] = artifact_ref
            result.content[0]['text'] = json.dumps(payload)
            result.artifact = artifact_ref
        
        return result
    return result


async def main():
    tools = await get_mcp_client()

    llm = ChatOpenAI(
        model="meta-llama/Llama-3.3-70B-Instruct",
        api_key=os.environ["DEEPINFRA_API_KEY"],
        base_url="https://api.deepinfra.com/v1/openai",
        temperature=0.3,
    )

    planner_agent = create_agent(   
        model = llm,
        system_prompt = 'You are a helpful assistant.',
        state_schema = MessagesState,
        tools = tools,
        middleware = [store_artifact],
        checkpointer = InMemorySaver()
    )
    
    return planner_agent