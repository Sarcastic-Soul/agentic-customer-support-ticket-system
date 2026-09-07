from langgraph.graph import END, StateGraph

from app.agent.checkpoint import get_checkpointer
from app.agent.nodes.act import act_node
from app.agent.nodes.answer import answer_node
from app.agent.nodes.classify import classify_node
from app.agent.nodes.plan import plan_node
from app.agent.nodes.prepare import prepare_node
from app.agent.nodes.respond import respond_node
from app.agent.nodes.retrieve import retrieve_node
from app.agent.state import AgentState

_graph = None


async def get_graph():
    """prepare -> classify -> plan -> retrieve -> act -> answer -> respond.
    hard_route/verify/escalate are Stage 6. Compiled once and cached - the
    checkpointer's pool is a long-lived resource, not something to recreate
    per call.
    """
    global _graph
    if _graph is not None:
        return _graph

    checkpointer = await get_checkpointer()

    builder = StateGraph(AgentState)
    builder.add_node("prepare", prepare_node)
    builder.add_node("classify", classify_node)
    builder.add_node("plan", plan_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("act", act_node)
    builder.add_node("answer", answer_node)
    builder.add_node("respond", respond_node)

    builder.set_entry_point("prepare")
    builder.add_edge("prepare", "classify")
    builder.add_edge("classify", "plan")
    builder.add_edge("plan", "retrieve")
    builder.add_edge("retrieve", "act")
    builder.add_edge("act", "answer")
    builder.add_edge("answer", "respond")
    builder.add_edge("respond", END)

    _graph = builder.compile(checkpointer=checkpointer)
    return _graph
