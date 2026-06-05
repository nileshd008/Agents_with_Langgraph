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
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, AnyMessage
from langchain.messages import ToolMessage, SystemMessage
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
from langgraph.types import Command
from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationError
from typing import Any, Dict, Optional, Literal, List
import pandas as pd
import uuid
import json
import plotly.io as pio
from pathlib import Path
import hashlib
from langgraph.prebuilt import InjectedStates
from langchain_core.tools import InjectedToolCallId
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from tools import *

def get_tools():
    tools = [update_state, get_artifact]
    mcp_tools = client.get_tools()
    for i in mcp_tools:
        tools.append(i)
    
    return tools

if __name__== '__main__':
    load_dotenv()

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
                },
            }
        }
    )


    planner_agent = create_agent(
        model = ChatLiteLLM(model = 'gemini/gemini-3.5-flash', temperature = 0.2),
        system_prompt = 'You are a helpful assistant.',
        state_schema = MainState,
        tools = get_tools(),
        middleware = [store_artifact],
        checkpointer = InMemorySaver()
    )