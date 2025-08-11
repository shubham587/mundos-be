from __future__ import annotations

from typing import Dict, Any

from langgraph.graph import StateGraph, END

from agent.nodes import node_follow_up, node_send_email, node_ai_summary


def build_graph():
    graph = StateGraph(dict)
    graph.add_node("follow_up", node_follow_up) # creates email
    graph.add_node("send_email", node_send_email) # sends email
    graph.add_node("ai_summary", node_ai_summary) # creates summary
    graph.set_entry_point("follow_up")
    graph.add_edge("follow_up", "send_email")
    graph.add_edge("send_email", "ai_summary")
    graph.add_edge("ai_summary", END)
    return graph.compile()


def run(patient: Dict[str, Any], campaign: Dict[str, Any]) -> Dict[str, Any]:
    app = build_graph()
    return app.invoke({"patient": patient, "campaign": campaign})


