from __future__ import annotations

from typing import Dict, Any

from langgraph.graph import StateGraph, END

from agent.nodes import node_follow_up, node_send_email, node_ai_summary, node_call_patient


def build_graph():
    graph = StateGraph(dict)
    graph.add_node("follow_up", node_follow_up)  # create content
    graph.add_node("send_email", node_send_email)  # send email
    graph.add_node("call_patient", node_call_patient)  # call patient
    graph.add_node("ai_summary", node_ai_summary)  # create summary
    graph.set_entry_point("follow_up")

    # Router based on campaign conditions
    def route_action(state: Dict[str, Any]) -> str:
        campaign = state.get("campaign") or {}
        channel_type = ((campaign.get("channel") or {}).get("type") or "").lower()
        if (
            campaign.get("campaign_type") == "RECOVERY"
            and campaign.get("status") == "ATTEMPTING_RECOVERY"
            and channel_type == "sms"
        ):
            return "call_patient"
        return "send_email"

    graph.add_conditional_edges("follow_up", route_action)
    graph.add_edge("call_patient", "ai_summary")
    graph.add_edge("send_email", "ai_summary")
    graph.add_edge("ai_summary", END)
    return graph.compile()


def run(patient: Dict[str, Any], campaign: Dict[str, Any]) -> Dict[str, Any]:
    app = build_graph()
    return app.invoke({"patient": patient, "campaign": campaign})


