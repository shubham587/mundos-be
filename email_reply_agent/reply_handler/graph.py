from __future__ import annotations

from typing import Dict, Any, Optional

from langgraph.graph import StateGraph, END

from .state import ReplyState
from .nodes import (
    load_patient_and_campaign,
    analyze_incoming,
    record_incoming_interaction,
    generate_booking_email,
    generate_disambiguation_email,
    generate_declined_email,
    query_knowledge_base,
    generate_answer_email,
    update_campaign_for_handoff,
    generate_handoff_email,
    send_reply_email,
    analyze_outgoing,
    record_outgoing_interaction,
    update_campaign_status,
    update_campaign_to_declined,
    ai_summary,
)


def build_graph():
    graph = StateGraph(ReplyState)

    graph.add_node("load_patient_and_campaign", load_patient_and_campaign)
    graph.add_node("analyze_incoming", analyze_incoming)
    graph.add_node("record_incoming_interaction", record_incoming_interaction)

    graph.add_node("generate_booking_email", generate_booking_email)
    graph.add_node("generate_disambiguation_email", generate_disambiguation_email)
    graph.add_node("generate_declined_email", generate_declined_email)
    graph.add_node("send_reply_email", send_reply_email)
    graph.add_node("query_knowledge_base", query_knowledge_base)
    graph.add_node("generate_answer_email", generate_answer_email)
    graph.add_node("update_campaign_for_handoff", update_campaign_for_handoff)
    graph.add_node("generate_handoff_email", generate_handoff_email)
    graph.add_node("analyze_outgoing", analyze_outgoing)
    graph.add_node("record_outgoing_interaction", record_outgoing_interaction)
    graph.add_node("update_campaign_status", update_campaign_status)
    graph.add_node("update_campaign_to_declined", update_campaign_to_declined)
    graph.add_node("ai_summary", ai_summary)

    graph.set_entry_point("load_patient_and_campaign")

    graph.add_edge("load_patient_and_campaign", "analyze_incoming")
    graph.add_edge("analyze_incoming", "record_incoming_interaction")

    def router(state: Dict[str, Any]) -> str:
        intent = state.get("classified_intent")
        if intent == "booking_request":
            campaign = state.get("campaign") or {}
            campaign_type = campaign.get("campaign_type")
            if campaign_type in {"RECOVERY", "RECALL"}:
                return "generate_booking_email"
        if intent == "service_denial":
            return "update_campaign_to_declined"
        if intent == "irrelevant_confused":
            return "generate_disambiguation_email"
        if intent == "question":
            return "query_knowledge_base"
        return "ai_summary"

    graph.add_conditional_edges("record_incoming_interaction", router)

    graph.add_edge("generate_booking_email", "send_reply_email")

    graph.add_edge("generate_disambiguation_email", "send_reply_email")
    graph.add_edge("update_campaign_to_declined", "generate_declined_email")
    graph.add_edge("generate_declined_email", "send_reply_email")
    # Question branch routing
    def answer_checker(state: Dict[str, Any]) -> str:
        answer = (state.get("kb_answer") or "").strip()
        if answer and answer != "NO_ANSWER":
            return "generate_answer_email"
        return "update_campaign_for_handoff"

    graph.add_conditional_edges("query_knowledge_base", answer_checker)
    graph.add_edge("generate_answer_email", "send_reply_email")
    graph.add_edge("update_campaign_for_handoff", "generate_handoff_email")
    graph.add_edge("generate_handoff_email", "send_reply_email")
    graph.add_edge("send_reply_email", "analyze_outgoing")
    graph.add_edge("analyze_outgoing", "record_outgoing_interaction")
    # Post-outgoing routing: booking branch updates status then summary; others go to summary directly
    def post_outgoing_router(state: Dict[str, Any]) -> str:
        if state.get("classified_intent") == "booking_request":
            campaign = state.get("campaign") or {}
            if campaign.get("campaign_type") in {"RECOVERY", "RECALL"}:
                return "update_campaign_status"
        return "ai_summary"

    graph.add_conditional_edges("record_outgoing_interaction", post_outgoing_router)
    graph.add_edge("update_campaign_status", "ai_summary")

    graph.add_edge("ai_summary", END)

    return graph.compile()


def run_reply_workflow(
    thread_id: str,
    reply_email_body: str,
    *,
    patient_email: Optional[str] = None,
    patient_name: Optional[str] = None,
    message_id: Optional[str] = None,
    inbound_subject: Optional[str] = None,
    inbound_references: Optional[str] = None,
) -> Dict[str, Any]:
    app = build_graph()
    initial_state: ReplyState = {
        "thread_id": thread_id,
        "reply_email_body": reply_email_body,
    }
    if patient_email:
        initial_state["patient_email"] = patient_email
    if patient_name:
        initial_state["patient_name"] = patient_name
    if message_id:
        initial_state["message_id"] = message_id
    if inbound_subject:
        initial_state["inbound_subject"] = inbound_subject
    if inbound_references:
        initial_state["inbound_references"] = inbound_references
    result = app.invoke(initial_state)
    return dict(result)
