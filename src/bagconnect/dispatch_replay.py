from .replay_policy import *  # noqa: F401,F403
from .replay_policy import (
    adoption_decision,
    adoption_gate,
    compare_named_policies,
    compare_policy_replay,
    replay_dispatch,
    score_schedule,
)

compare_dispatch_policies = compare_policy_replay
dispatch_replay_review = compare_policy_replay
review_dispatch = compare_policy_replay
policy_replay = compare_policy_replay
evaluate_adoption = adoption_gate
decide_adoption = adoption_decision
enablement_basis = adoption_decision

__all__ = [
    'adoption_gate', 'adoption_decision', 'compare_named_policies', 'compare_policy_replay',
    'replay_dispatch', 'score_schedule', 'compare_dispatch_policies',
    'dispatch_replay_review', 'review_dispatch', 'policy_replay',
    'evaluate_adoption', 'decide_adoption', 'enablement_basis',
]
