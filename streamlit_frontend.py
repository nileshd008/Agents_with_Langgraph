import streamlit as st
from agent import main
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, AnyMessage, ToolMessage, SystemMessage
import asyncio
from threading import Thread

config = {'configurable':{'thread_id': 'thread-4','user_id': 'nil'}, 'user_id': 'nil'}

def start_background_loop():
    loop = asyncio.new_event_loop()
    t = Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop

if "loop" not in st.session_state:
    st.session_state['loop'] = start_background_loop()

if "ai_agent" not in st.session_state:
    st.session_state['ai_agent'] = None
    print('ai_agent')

if st.session_state['ai_agent'] is None:
    with st.spinner("Initializing MCP Client and Agent..."):
        try:
            future = asyncio.run_coroutine_threadsafe(main(), st.session_state['loop'])
            st.session_state['ai_agent'] = future.result() 
        except Exception as e:
            st.error(f"Failed to initialize agent: {e}")
            st.stop()

async def get_state(agent, config):
    return await agent.aget_state(config)

async def task(agent, msg, config):
    return await agent.ainvoke({"messages": [HumanMessage(content = msg)]}, config)

messages = asyncio.run_coroutine_threadsafe(get_state(st.session_state['ai_agent'], config), st.session_state['loop']).result().values.get('messages', [])

for message in messages:
    if isinstance(message, HumanMessage):
        with st.chat_message('user'):
            st.text(message.content)

    if isinstance(message, AIMessage):
        with st.chat_message('assistant'):
            st.text(message.content)

input = st.chat_input('Describe your query')

if input:
    with st.chat_message('user'):
        st.text(input)
    
    if st.session_state.get('ai_agent') is not None and st.session_state.get('loop') is not None:
        result = asyncio.run_coroutine_threadsafe(task(st.session_state.get('ai_agent'), input, config), st.session_state['loop']).result()

    with st.chat_message('assistant'):
        st.text(result['messages'][-1].content)



