from langgraph.graph import END, StateGraph

from app.agent.checkpoint import get_checkpointer
from app.agent.nodes.act import act_node
from app.agent.nodes.answer import answer_node
from app.agent.nodes.classify import classify_node
from app.agent.nodes.escalate import escalate_node, route_after_escalate
from app.agent.nodes.hard_route import hard_route_node, route_after_hard_route
from app.agent.nodes.plan import plan_node
from app.agent.nodes.prepare import prepare_node
from app.agent.nodes.respond import respond_node
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.verify import route_after_verify, verify_node
from app.agent.state import AgentState

_graph = None


async def get_graph():
    """prepare -> classify -> hard_route -[escalate|plan]
    plan -> retrieve -> act -> answer -> verify -[escalate|answer(repair)|respond]
    escalate -[answer(resume, human note)|END]
    respond -> END

    Compiled once and cached - the checkpointer's pool is a long-lived
    resource, not something to recreate per call.
    """
    global _graph
    if _graph is not None:
        return _graph

    checkpointer = await get_checkpointer()

    builder = StateGraph(AgentState)
    builder.add_node("prepare", prepare_node)
    builder.add_node("classify", classify_node)
    builder.add_node("hard_route", hard_route_node)
    builder.add_node("plan", plan_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("act", act_node)
    builder.add_node("answer", answer_node)
    builder.add_node("verify", verify_node)
    builder.add_node("escalate", escalate_node)
    builder.add_node("respond", respond_node)

    builder.set_entry_point("prepare")
    builder.add_edge("prepare", "classify")
    builder.add_edge("classify", "hard_route")
    builder.add_conditional_edges(
        "hard_route", route_after_hard_route, {"escalate": "escalate", "plan": "plan"}
    )
    builder.add_edge("plan", "retrieve")
    builder.add_edge("retrieve", "act")
    builder.add_edge("act", "answer")
    builder.add_edge("answer", "verify")
    builder.add_conditional_edges(
        "verify",
        route_after_verify,
        {"escalate": "escalate", "answer": "answer", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "escalate", route_after_escalate, {"answer": "answer", "end": END}
    )
    builder.add_edge("respond", END)

    _graph = builder.compile(checkpointer=checkpointer)
    return _graph
