"""Wire up the CAMEL Workforce that drives auto-research over OASIS sims.

Pattern:
    Planner (frontier) ──▶ Coordinator (frontier)
                                │
              ┌─────────────────┼──────────────────┬─────────────────┐
              ▼                 ▼                  ▼                 ▼
       Literature Worker  Scenario Designer  Math Analyst       Report Writer
       (search tools)     (file write tools) (code exec tools)  (file write)
"""
from __future__ import annotations

from camel.agents import ChatAgent
from camel.societies.workforce import Workforce
from camel.toolkits import (
    CodeExecutionToolkit,
    FileWriteToolkit,
    SearchToolkit,
)

from src.auto_research import prompts
from src.model_factory import make_model


def build_workforce(description: str = "OASIS deep-research workforce") -> Workforce:
    # ─── coordinator + planner (frontier model) ────────────────────────────
    coordinator = ChatAgent(
        system_message="You coordinate worker assignment for an OASIS deep-research workforce.",
        model=make_model("coordinator"),
    )
    task_agent = ChatAgent(
        system_message=prompts.PLANNER,
        model=make_model("planner"),
    )

    wf = Workforce(
        description=description,
        coordinator_agent=coordinator,
        task_agent=task_agent,
    )

    # ─── literature search worker ──────────────────────────────────────────
    search_tools = SearchToolkit().get_tools()
    wf.add_single_agent_worker(
        description="Literature search worker: finds peer-reviewed prior work.",
        worker=ChatAgent(
            system_message=prompts.LITERATURE_WORKER,
            model=make_model("literature_worker"),
            tools=search_tools,
        ),
    )

    # ─── scenario designer ─────────────────────────────────────────────────
    file_tools = FileWriteToolkit().get_tools()
    wf.add_single_agent_worker(
        description="Scenario designer: emits OASIS run specs as JSON.",
        worker=ChatAgent(
            system_message=prompts.SCENARIO_DESIGNER,
            model=make_model("scenario_designer"),
            tools=file_tools,
        ),
    )

    # ─── math analyst (can execute python) ────────────────────────────────
    code_tools = CodeExecutionToolkit(sandbox="subprocess", verbose=False).get_tools()
    wf.add_single_agent_worker(
        description=(
            "Math analyst: fits SIR/Hawkes/Deffuant/Bayesian-AB to OASIS .db outputs. "
            "Uses src.analysis.metrics and src.models.*."
        ),
        worker=ChatAgent(
            system_message=prompts.MATH_ANALYST,
            model=make_model("math_analyst"),
            tools=code_tools + file_tools,
        ),
    )

    # ─── report writer ─────────────────────────────────────────────────────
    wf.add_single_agent_worker(
        description="Report writer: produces the final Markdown deliverable.",
        worker=ChatAgent(
            system_message=prompts.REPORT_WRITER,
            model=make_model("report_writer"),
            tools=file_tools,
        ),
    )

    return wf
