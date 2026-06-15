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
from store_module import get_artifact_store, saver
import asyncio
from langchain.agents.middleware import wrap_tool_call, after_model
from langchain.tools.tool_node import ToolCallRequest
from langgraph.prebuilt.tool_node import ToolRuntime
from langchain_core.tools import tool
from langchain.tools import InjectedState
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.tools import InjectedToolCallId
from langchain_deepinfra import ChatDeepInfra
from langchain_openai import ChatOpenAI
from langchain.agents.structured_output import ToolStrategy, ProviderStrategy
from prompt import VISUALIZATION_PROMPT, SQL_SPECIALIST_PROMPT, ROUTING_PROMPT
from langgraph.runtime import Runtime
import re

load_dotenv()

checkstore = None
tools = None
sql_agent = None
visualization_agent = None
sql_tools = None
viz_tools = None
visulaization_agent = None


llm = ChatOpenAI(
        model="deepseek-ai/DeepSeek-V3",
        api_key=os.environ["DEEPINFRA_API_KEY"],
        base_url="https://api.deepinfra.com/v1/openai",
        temperature=0.3,
    )

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


async def get_artifact_exec(artifactid, user_id, type: str):
    async with get_artifact_store() as store:
        result = await store.aget((type, user_id), artifactid)
    return result

@tool
async def get_artifact(artifact_id: str, runtime: ToolRuntime):
    """
    Load artifact using artifact_id.
    
    """
    result = await get_artifact_exec(artifactid = artifact_id, user_id = runtime.config["configurable"]["user_id"], type = 'manifest')
    manifest = result.value

    if manifest['mime_type'] == '"application/json"':
        result = await get_artifact_exec(artifactid = artifact_id, user_id = runtime.config["configurable"]["user_id"], type = 'artifact')
        data = result.value
        return {'messages': [ToolMessage(content = json.dumps(
            {
                'artifact_id': artifact_id,
                'artifact_type': 'json',
                'data': data
            },
            ensure_ascii = False,
            default = str
        )
        )]}

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
        
            data = json.dumps(payload['data'])
            artifact_id = hashlib.sha256(data.encode('utf-8')).hexdigest()

            await save_artifact(data, user_id = config['user_id'], artifact_id = artifact_id)

            mime_type = "application/json"
            artifact_type = "json"

            await save_artifact({
                    "schema_version": "1.0",
                    'description': 'Database Table schema',
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "mime_type": mime_type,
                    "source_tool_name": request.tool_call['name'],
                    "source_tool_call_id": request.tool_call['id'],
                    "visibility": 'assistant',
                    "rendering": False
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
                "visibility": 'assistant',
                "rendering": False
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
                    "source_tool_call_id": request.tool_call['id'],
                    "visibility": 'user',
                    "rendering": True
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
                'uri': f"http://localhost:8000/view/{config['user_id']}/{artifact_id}",
                "visibility": 'user',
                "rendering": True
            }
            
            payload['data'] = artifact_ref
            result.content[0]['text'] = json.dumps(payload)
            result.artifact = artifact_ref
        return result
    return result

class MainRouter(BaseModel):
    model_config = ConfigDict(extra = 'ignore')

    intent: Literal['SQL_ONLY', 'SQL_AND_VIZ',  'CLARITY'] = Field(description = """Intent Extracted from current user query.
                                                                  - 'SQL_ONLY': if intent is only to generate sql query from user query.
                                                                  - 'SQL_AND_VIZ': if user intent is to generate sql and visulaize data in graph or plot form.
                                                                  - 'CLARITY': if need more clarification to generate sql.""",)
    last_validated_sql: Optional[str] = Field(
        description="""
        Final validated SQL query generated by SQL_SPECIALIST tool.
        Update ONLY after SQL is successfully validated.
        """
    )
    table_schema_artifact: str = Field(
        description="""
        Artifact Id of table schema in database.
        """
    )
    current_invocation_query: str = Field(
        description="""
        Latest user query.
        MUST always contain the current user input.
        """
    )
    last_invocation_query: Optional[str] = Field(
        description="""
        Previous user query.
        Before updating current_invocation_query, copy its old value here.
        """,
        default = None
    )
    user_session_summary: Optional[str] = Field(
        description="""
        Compact summary of entire conversation so far.
        Update after every user interaction.
        Keep it short but meaningful.
        """
    )
    viz_requested: Optional[Literal["bar_chart", "line_chart", "pie_chart", "table", "none"]] = Field(
        description="""
        Type of visualization requested by user.

        Explicit VIX Keywards:
        plot, chart, graph, visulaization, dashboard, trend line, bar chart, line chart, scatter, histogram.

        Choose:
        - bar_chart: comparison across categories
        - line_chart: trends over time
        - pie_chart: proportions
        - table: tabular output requested
        - none: no visualization requested

        If user does not explicitly mention visualization, use 'none'.
        """,
        default = None
    )
    clarifying_question: Optional[str] = Field(
        description="""
        Ask a question ONLY if user query is ambiguous or missing required info
        to generate SQL.

        Examples:
        - missing table
        - unclear column
        - ambiguous metric

        If query is clear → set to "Cleared".
        """,
        default = None
    )
    MAX_RETRIES: int = 3
    MAX_VIZ_RETRIES: int = 3
    assumptions: Optional[str] = Field(description = "assumption for final generated sql query")
    final_query_status: Literal['SUCCESS', 'FAIL_NEEDS_CLARIFICATION', 'FAIL_MAX_RETRIES'] = Field(description = 'status of generated sql query')
    VIZ_STATUS: Literal['SUCCESS','FAIL_MAX_RETRIES'] = Field(description = """Status of visulaization agent""")
    VIZ_artifact: Optional[str] = Field(description = """Arifact ID of visualization.""", default = None)


class PlnnerState(MainRouter):
    model_config = ConfigDict(extra='ignore')
    messages: Annotated[List[dict], add_messages]

class SqlState(MainRouter):
    model_config = ConfigDict(extra='ignore')
    messages: Annotated[List[dict], add_messages]

class VisualizeState(MainRouter):
    model_config = ConfigDict(extra='ignore')
    messages: Annotated[List[dict], add_messages] 

@tool(args_schema=MainRouter)
async def update_state(runtime: ToolRuntime, **kwargs):
    """Update the application state with specific allowed keys."""
    try:
        patch = MainRouter(**kwargs)
        return Command(update = {**patch.model_dump(exclude_unset = True, exclude_none = True),
                                'messages': [ToolMessage(content = 'State Updated Successfully', tool_call_id = runtime.tool_call_id)]})
    except Exception as e:
        return {'messages': [ToolMessage(content = f'update schema error: {str(e)}')]}

@tool
async def get_state(runtime: ToolRuntime):
    "get values of state variables"
    try:
        return {'messages': [ToolMessage(content = json.dumps({k: v for k, v in runtime.state.items() if k not in ('messages')}), tool_call_id = runtime.tool_call_id)]}
    
    except Exception as e:
        return {'messages': [ToolMessage(content = f'update schema error: {str(e)}', tool_call_id = runtime.tool_call_id)]}

@tool
async def sql_specialist(query: str, runtime: ToolRuntime):
    """You are specialized text-to-sql Agent to Generate SQL query from user question."""
    
    try:
        clean_state = {k: v for k, v in runtime.state.items() if k not in ('messages')}
        sub_agent_input = {**clean_state, 'messages': [HumanMessage(content = query)]}
        
        sub_config = copy.deepcopy(runtime.config)
        sub_config['configurable']['thread_id'] = 'thread-sql-' + re.search(r'\-(\d+)$', runtime.config['configurable']['thread_id']).group(1)

        result = await sql_agent.ainvoke(sub_agent_input, config = sub_config)
        return Command(update = {**result.model_dump(exclude={"messages"}),
                                'messages': [ToolMessage(content = result['messages'][-1].content, tool_call_id = runtime.tool_call_id)]})
        
    except Exception as e:
        return {'messages': [ToolMessage(content = f'update schema error: {str(e)}', tool_call_id = runtime.tool_call_id)]}

@tool
async def visualization_tool(query: str, runtime: ToolRuntime):
    """
    You are specialized Visualizer + Validator for sql query using plotly.
    args:
        query - instructions to visualization agent
    """
    try:
        clean_state = {k: v for k, v in runtime.state.items() if k not in ('messages')}

        viz_config = copy.deepcopy(runtime.config)
        viz_config['configurable']['thread_id'] = 'thread-visual-' + re.search(r'\-(\d+)$', runtime.config['configurable']['thread_id']).group(1)

        result = await visulaization_agent.ainvoke({**clean_state, 'messages' : [HumanMessage(content = query)]}, config = viz_config)

        return Command(update = {**result.model_dump(exclude={"messages"}),
                                'messages': [ToolMessage(content = result['messages'][-1].content, tool_call_id = runtime.tool_call_id)]})
    except Exception as e:
        return {'messages': [ToolMessage(content = f'update schema error: {str(e)}')]}


async def main():
    global checkstore, tools, sql_tools, viz_tools, llm, llm_2, visualization_agent, sql_agent, visulaization_agent

    try:
        checkstore = await saver()
        tools = await get_mcp_client()
        sql_tools = copy.deepcopy(tools)
        viz_tools = copy.deepcopy(tools)

        tools.append(sql_specialist)
        tools.append(visualization_tool)

        tools.append(update_state)
        sql_tools.append(update_state)
        viz_tools.append(update_state)

        tools.append(get_state)
        sql_tools.append(get_state)
        viz_tools.append(get_state)

        tools.append(get_artifact)
        sql_tools.append(get_artifact)
        viz_tools.append(get_artifact)
        
        sql_agent = create_agent(
            model = llm,
            system_prompt = SQL_SPECIALIST_PROMPT,
            state_schema = SqlState,
            tools = sql_tools,
            middleware = [store_artifact],
            checkpointer = checkstore
        )

        visualization_agent = create_agent(
            model = llm,
            system_prompt = VISUALIZATION_PROMPT,
            state_schema = VisualizeState,
            tools = viz_tools,
            middleware = [store_artifact],
            checkpointer = checkstore
        )

        planner_agent = create_agent(   
            model = llm,
            system_prompt = ROUTING_PROMPT,
            state_schema = PlnnerState,
            tools = tools,
            middleware = [store_artifact],
            checkpointer = checkstore
        )
        
        return planner_agent
        
    except Exception as e:
        return None

    
    





