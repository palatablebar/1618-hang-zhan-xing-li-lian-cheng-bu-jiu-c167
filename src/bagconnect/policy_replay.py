from .replay_policy import *  # noqa: F401,F403
from .replay_policy import compare_policy_replay as replay
from .replay_policy import compare_policy_replay, compare_named_policies, adoption_gate

compare_strategies = compare_policy_replay
review = compare_policy_replay

__all__ = ['replay', 'compare_policy_replay', 'compare_named_policies',
           'adoption_gate', 'compare_strategies', 'review']
