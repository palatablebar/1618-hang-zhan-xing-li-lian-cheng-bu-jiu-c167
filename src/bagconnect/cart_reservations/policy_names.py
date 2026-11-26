POLICY_ALIASES = {
    'baseline': 'early_run',
    'original': 'early_run',
    'early': 'early_run',
    'early_run': 'early_run',
    'earliest': 'deadline_first',
    'earliest_closeout': 'deadline_first',
    'earliest_first': 'deadline_first',
    'closeout_first': 'deadline_first',
    'deadline': 'deadline_first',
    'deadline_first': 'deadline_first',
    'risk': 'risk_first',
    'risk_first': 'risk_first',
    'risk_aware': 'risk_first',
    'high_risk': 'risk_first',
    'new': 'risk_guard',
    'candidate': 'risk_guard',
    'risk_guard': 'risk_guard',
    'earliest_guard': 'risk_guard',
    'guard': 'risk_guard',
    'guarded': 'risk_guard',
    'guarded_risk': 'risk_guard',
    'protected_risk': 'risk_guard',
    'risk_protected': 'risk_guard',
    'safe_risk': 'risk_guard',
    'risk_balanced': 'risk_guard',
    'closeout_guard': 'risk_guard',
}

CHINESE_POLICY_ALIASES = {
    '最早截关': 'deadline_first',
    '截关优先': 'deadline_first',
    '最早截关单': 'deadline_first',
    '风险优先': 'risk_first',
    '高风险优先': 'risk_first',
    '风险保护': 'risk_guard',
    '保护最早截关': 'risk_guard',
    '风险均衡': 'risk_guard',
    '新排法': 'risk_guard',
}


def normalize_policy(value: str | None) -> str:
    if value is None:
        return 'early_run'
    raw = str(value).strip()
    if raw in CHINESE_POLICY_ALIASES:
        return CHINESE_POLICY_ALIASES[raw]
    token = raw.lower().replace('-', '_').replace(' ', '_')
    return POLICY_ALIASES.get(token, POLICY_ALIASES.get(raw, token))
