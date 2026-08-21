"""The compiled state machine. Mirrors docs/05's graph, extended with the
debug-loop nodes described in the plan: prepare_workspace, locate_code,
evaluate_fixes, apply_patch, static_check, generate_tests(+run_tests),
push_branch. `services/` stays framework-free; this is the only file that
imports langgraph."""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from haaland.agent import routing
from haaland.agent.nodes.apply_patch import apply_patch_node
from haaland.agent.nodes.classify import classify_node
from haaland.agent.nodes.diagnose import diagnose_node
from haaland.agent.nodes.escalate_manual import escalate_manual_node
from haaland.agent.nodes.evaluate_fixes import evaluate_fixes_node
from haaland.agent.nodes.file_ticket import file_ticket_node
from haaland.agent.nodes.generate_report import generate_report_node
from haaland.agent.nodes.generate_tests import generate_tests_node
from haaland.agent.nodes.ingest_input import ingest_input_node
from haaland.agent.nodes.locate_code import locate_code_node
from haaland.agent.nodes.open_pr import open_pr_node
from haaland.agent.nodes.prepare_workspace import prepare_workspace_node
from haaland.agent.nodes.push_branch import push_branch_node
from haaland.agent.nodes.redact import redact_node
from haaland.agent.nodes.request_approval import request_approval_node
from haaland.agent.nodes.run_tests import run_tests_node
from haaland.agent.nodes.static_check import static_check_node
from haaland.agent.state import IncidentState


def build_graph(deps, checkpointer):
    max_attempts = deps.settings.max_fix_attempts
    g = StateGraph(IncidentState)

    def bind(node_fn):
        return partial(node_fn, deps=deps)

    g.add_node("ingest_input", bind(ingest_input_node))
    g.add_node("redact", bind(redact_node))
    g.add_node("classify", bind(classify_node))
    g.add_node("file_ticket", bind(file_ticket_node))
    g.add_node("prepare_workspace", bind(prepare_workspace_node))
    g.add_node("locate_code", bind(locate_code_node))
    g.add_node("diagnose", bind(diagnose_node))
    g.add_node("evaluate_fixes", bind(evaluate_fixes_node))
    g.add_node("apply_patch", bind(apply_patch_node))
    g.add_node("static_check", bind(static_check_node))
    g.add_node("generate_tests", bind(generate_tests_node))
    g.add_node("run_tests", bind(run_tests_node))
    g.add_node("push_branch", bind(push_branch_node))
    g.add_node("open_pr", bind(open_pr_node))
    g.add_node("request_approval", bind(request_approval_node))
    g.add_node("escalate_manual", bind(escalate_manual_node))
    g.add_node("generate_report", bind(generate_report_node))

    g.add_edge(START, "ingest_input")
    g.add_edge("ingest_input", "redact")
    g.add_edge("redact", "classify")
    g.add_conditional_edges(
        "classify",
        partial(routing.route_by_severity, ticket_only=deps.settings.ticket_only_severity_set),
        {"low": "file_ticket", "high": "prepare_workspace"},
    )
    g.add_edge("file_ticket", END)

    g.add_edge("prepare_workspace", "locate_code")
    g.add_edge("locate_code", "diagnose")
    g.add_conditional_edges(
        "diagnose",
        routing.route_by_diagnosis_confidence,
        {"confident": "evaluate_fixes", "escalate": "escalate_manual"},
    )

    g.add_edge("evaluate_fixes", "apply_patch")
    g.add_edge("apply_patch", "static_check")
    g.add_conditional_edges(
        "static_check",
        partial(routing.route_by_static_check, max_attempts=max_attempts),
        {"pass": "generate_tests", "retry": "evaluate_fixes", "exhausted": "escalate_manual"},
    )

    g.add_edge("generate_tests", "run_tests")
    g.add_conditional_edges(
        "run_tests",
        partial(routing.route_by_test_outcome, max_attempts=max_attempts),
        {"proceed": "push_branch", "retry": "evaluate_fixes", "exhausted": "escalate_manual"},
    )

    g.add_edge("push_branch", "open_pr")
    g.add_edge("open_pr", "request_approval")
    g.add_conditional_edges(
        "request_approval",
        routing.route_by_approval,
        {"approved": "generate_report", "rejected": "evaluate_fixes", "escalated": "request_approval"},
    )

    g.add_edge("escalate_manual", "generate_report")
    g.add_edge("generate_report", END)

    return g.compile(checkpointer=checkpointer)
