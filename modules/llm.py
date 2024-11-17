from langchain_core.messages import HumanMessage, SystemMessage
from typing_extensions import Annotated, TypedDict
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder
)
from langsmith import traceable
from langgraph.graph import START, StateGraph
from langchain_ollama import ChatOllama
from typing import Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

chat_ollama = ChatOllama(
    base_url="http://192.168.1.125:11434",
    model="llama3.1:8b",
    temperature=0.8
)
class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_prompt: str

workflow = StateGraph(state_schema=State)

prompt = ChatPromptTemplate.from_messages(
    messages=[SystemMessage("""
    You are a humorous AI responsible for generating ridiculous explanations for unexpected events. 
    Your task is to come up with a reason why a safety car would be deployed during a motor 
    racing event. 
    Your response should be a single phrase that explains why the safety car was deployed. 
    Keep it to less than 100 characters.
    
    Some good examples include:
    - Somebody spilled beer on the track and the marshals are cleaning it up.
    - The race director fell asleep and hit the red button by mistake.
"""),
              MessagesPlaceholder(variable_name="user_prompt")],
)

@traceable
def call_model(state: State):
    chain = prompt | chat_ollama
    response = chain.invoke({
        "messages": state["messages"],
        "user_prompt": state["user_prompt"]
    }
    )
    return {"messages": [response]}


workflow.add_edge(START, "model")
workflow.add_node("model", call_model)


def generate_caution_reason(llm_prompt: str = "Why was the safety car deployed at Le Mans?") -> str:
    app = workflow.compile()
    response = app.invoke(
        {'user_prompt': [HumanMessage(content=llm_prompt)]},
        {'configurable': {'thread_id': 0}}
    )
    return response["messages"][-1].content
