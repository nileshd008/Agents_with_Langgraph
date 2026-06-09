import streamlit as st
from a import get_planner_agent, execute_agent
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, AnyMessage, ToolMessage, SystemMessage


if 'message_history' not in st.session_state:
    st.session_state['message_history'] = []


for message in st.session_state['message_history']:
    with st.chat_message(message['role']):
        st.text(message['content'])


input = st.chat_input('Describe your query')

@st.cache_resource
def load_backend_agent():
    return get_planner_agent()

ai_agent = load_backend_agent()


config = {'configurable':{'thread_id': 'thread-1','user_id': 'nil'}, 'user_id': 'nil'}
if input:
    st.session_state['message_history'].append({'role': 'user', 'content': input})
    with st.chat_message('user'):
        st.text(input)
    
    result = execute_agent(ai_agent, {'messages': [HumanMessage(content=input)]}, config = config)

    res = result['messages'][-1].content

    st.session_state['message_history'].append({'role': 'assistant', 'content': res})
    with st.chat_message('assistant'):
        st.text(res)



