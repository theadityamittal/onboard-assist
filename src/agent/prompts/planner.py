"""Planner prompt builder — plan generation and replanning prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from state.models import OnboardingPlan


def build_replan_prompt(*, plan: OnboardingPlan, reason: str) -> list[dict[str, Any]]:
    """Build messages for replanning."""
    return [
        {"role": "system", "content": f"Rewrite the onboarding plan. Reason: {reason}"},
        {
            "role": "user",
            "content": f"Current plan has {len(plan.steps)} steps, version {plan.version}.",
        },
    ]


def build_plan_generation_prompt(
    *, role: str, user_name: str, key_facts: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Build messages for initial plan generation."""
    return [
        {
            "role": "system",
            "content": f"Generate an onboarding plan for {user_name} in the {role} role.",
        },
    ]
