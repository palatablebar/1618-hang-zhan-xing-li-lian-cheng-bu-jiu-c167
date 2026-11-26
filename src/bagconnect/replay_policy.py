"""Point-in-time replay of dispatch policies and their confirmed-missed coverage.

The prediction path only consumes measurements that were visible on the business
day.  Outcome rows may arrive later; they are kept in a separate label ledger
and are used for scoring/adoption, never as model inputs.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import Iterable

from .cart_reservations.contracts import Booking, Candidate, Disposition, Scenario
from .cart_reservations.service import allocate
from .cart_reservations.policy_names import normalize_policy as normalize_policy_name
from .closeout_windows.contracts import Windows
from .closeout_windows.service import snapshot
from .gate_calibration.contracts import Adjustment, ValidationPoint
from .gate_calibration.metrics import classification
from .missed_transfer.service import estimate
from .transfer_signals.service import prepare_all

PIECES_PER_UNIT = 5

POLICY_ALIASES = {
    'baseline': 'early_run',
    'original': 'early_run',
    'early': 'early_run',
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


def normalize_policy(value: str | None) -> str:
    return normalize_policy_name(value)


def deadline_of(record) -> int:
    return int(record.arrival) + int(record.window)


def shift_visible_ticket(tickets: Iterable, key: str, day: int):
    """Latest revision received by the end of the ticket's own business day."""
    view = snapshot(tuple(tickets), int(day) + 1)
    return next((row for row in view.accepted if row.key == key), None)


def outcome_ledger(tickets: Iterable, windows: Windows = Windows()) -> dict[str, dict]:
    """Resolve the latest business outcome without feeding it to the model."""
    # A cutoff beyond every legal day/receipt resolves all late reports for scoring.
    latest = snapshot(tuple(tickets), 10**9)
    accepted = {row.key: row for row in latest.accepted}
    ledger: dict[str, dict] = {}
    for key, row in accepted.items():
        reported = bool(row.complete and row.target is not None)
        missed = bool(reported and row.target >= 0.5)
        late = bool(row.outcome_day is not None and row.outcome_day >= windows.asof)
        post_window = bool(row.outcome_day is not None and row.outcome_day >= windows.holdout_end)
        after_shift = bool(row.outcome_day is not None and row.outcome_day > row.day)
        ledger[key] = {
            'reported': reported,
            'confirmed': reported,
            'confirmed_missed': missed,
            'observed': int(row.target) if reported else None,
            'outcome_day': row.outcome_day,
            'late_report': late,
            'late_return': late,
            'post_window_report': post_window,
            'after_shift_report': after_shift,
            'unreported': not reported,
            'complete': bool(row.complete),
        }
    for key in latest.conflicts:
        ledger[key] = {
            'reported': False,
            'confirmed': False,
            'confirmed_missed': False,
            'observed': None,
            'outcome_day': None,
            'late_report': False,
            'late_return': False,
            'post_window_report': False,
            'after_shift_report': False,
            'unreported': True,
            'conflict': True,
            'complete': False,
        }
    return ledger


def point_in_time_scoring_records(tickets: Iterable, all_tickets: Iterable) -> tuple:
    """Use shift-visible measurements while retaining later labels for scoring."""
    resolved = []
    all_tickets = tuple(all_tickets)
    for scoring in tickets:
        visible = shift_visible_ticket(all_tickets, scoring.key, scoring.day)
        if visible is None:
            continue
        # Labels are deliberately attached only after feature derivation is frozen.
        resolved.append(replace(
            visible,
            target=scoring.target,
            outcome_day=scoring.outcome_day,
            confirmed=scoring.confirmed,
            complete=scoring.complete,
        ))
    return tuple(resolved)


def build_replay_candidates(batch, windows: Windows = Windows(),
                            scenario: Scenario | None = None) -> tuple[Candidate, ...]:
    holdout = batch.vintage.holdout
    keys = sorted({
        row.key for row in batch.vintage.snapshot.accepted
        if row.phase == 'history' and holdout.lower <= row.day < holdout.upper
        and (scenario is None or not scenario.region or row.region == scenario.region)
    })
    visible = []
    for key in keys:
        source = next(row for row in batch.vintage.snapshot.accepted if row.key == key)
        row = shift_visible_ticket(batch.report.tickets, key, source.day)
        if row is not None:
            if scenario is None or not scenario.region or row.region == scenario.region:
                visible.append(row)
    prepared = prepare_all(batch.profile, tuple(visible))
    adjustment = batch.replay.adjustment
    candidates = []
    for item in prepared:
        raw = estimate(batch.fitted, item) if item.can_score() else None
        value = adjustment.apply(raw) if raw is not None else None
        plan = __import__('bagconnect.cart_reservations.service', fromlist=['draft']).draft(
            item, value, adjustment.radius)
        candidates.append(Candidate(plan, value, None, ()))
    return tuple(candidates)


def covered_pieces(record, booking: Booking | None) -> int:
    if booking is None or booking.state != Disposition.BOOKED or booking.assigned <= 0:
        return 0
    bags = record.raw[2]
    capacity_pieces = booking.assigned * PIECES_PER_UNIT
    if bags is None:
        # Do not invent missing piece counts; unit coverage remains available.
        return 0
    return max(0, min(int(bags), capacity_pieces))


def _booking_rows(schedule) -> dict[str, Booking]:
    return {row.key: row for row in schedule.rows}


def earliest_closeout_keys(schedule, *, only_earliest: bool = True) -> tuple[str, ...]:
    booked = [row for row in schedule.rows if row.state == Disposition.BOOKED]
    if not booked:
        return ()
    deadlines = {row.key: deadline_of(row.candidate.draft.signal.record) for row in booked}
    if only_earliest:
        first = min(deadlines.values())
        return tuple(sorted(key for key, value in deadlines.items() if value == first))
    return tuple(sorted(deadlines, key=lambda key: (deadlines[key], key)))


def score_schedule(schedule, candidates: tuple[Candidate, ...], labels: dict[str, dict]) -> dict:
    rows = _booking_rows(schedule)
    items = []
    totals = {
        'total': len(candidates), 'booked_orders': 0, 'booked_units': schedule.used,
        'wait_orders': 0,
        'manual_orders': 0, 'normal_orders': 0, 'locked_orders': 0,
        'reported': 0, 'unreported': 0, 'late_reports': 0,
        'post_window_reports': 0, 'confirmed_missed_total': 0,
        'covered_confirmed_missed': 0, 'covered_confirmed_missed_cases': 0,
        'covered_confirmed_missed_pieces': 0, 'covered_late_confirmed_missed': 0,
        'unreported_booked': 0, 'missing_piece_bookings': 0,
    }
    for candidate in candidates:
        record = candidate.draft.signal.record
        key = record.key
        booking = rows.get(key)
        label = labels.get(key, {'reported': False, 'confirmed_missed': False,
                                 'unreported': True, 'late_report': False})
        booked = bool(booking and booking.state == Disposition.BOOKED and booking.assigned > 0)
        if booking is not None and booking.state in (
                Disposition.WAIT, Disposition.MANUAL, Disposition.NORMAL, Disposition.LOCKED):
            totals[f'{booking.state}_orders'] += 1
        pieces = covered_pieces(record, booking)
        if booked:
            totals['booked_orders'] += 1
            if record.raw[2] is None:
                totals['missing_piece_bookings'] += 1
        if label.get('reported'):
            totals['reported'] += 1
        if label.get('unreported'):
            totals['unreported'] += 1
        if label.get('late_report'):
            totals['late_reports'] += 1
        if label.get('post_window_report'):
            totals['post_window_reports'] += 1
        if label.get('confirmed_missed'):
            totals['confirmed_missed_total'] += 1
            if booked:
                totals['covered_confirmed_missed_cases'] += 1
                totals['covered_confirmed_missed_pieces'] += pieces
                if label.get('late_report'):
                    totals['covered_late_confirmed_missed'] += pieces
        if label.get('unreported') and booked:
            totals['unreported_booked'] += 1
        items.append({
            'key': key, 'region': record.region, 'day': record.day,
            'deadline': deadline_of(record), 'bags': record.raw[2],
            'status': booking.state if booking else 'excluded',
            'units': booking.assigned if booking else 0,
            'start': booking.start if booking else None,
            'end': booking.end if booking else None,
            'risk': round(candidate.estimate, 6) if candidate.estimate is not None else None,
            'booked': booked, 'covered_pieces': pieces,
            'reported': label.get('reported', False),
            'unreported': label.get('unreported', True),
            'late_report': label.get('late_report', False),
            'confirmed_missed': label.get('confirmed_missed', False),
        })
    totals['covered_confirmed_missed'] = totals['covered_confirmed_missed_pieces']
    totals['unreported_count'] = totals['unreported']
    totals['waiting_orders'] = totals['wait_orders']
    totals['unreported_orders'] = totals['unreported']
    totals['not_reported'] = totals['unreported']
    totals['incomplete'] = totals['unreported']
    totals['late_report_count'] = totals['late_reports']
    totals['late_return_count'] = totals['late_reports']
    totals['post_window_report_count'] = totals['post_window_reports']
    denominator = totals['confirmed_missed_total']
    totals['coverage_rate'] = (totals['covered_confirmed_missed_cases'] / denominator
                               if denominator else None)
    return {**totals, 'items': sorted(items, key=lambda row: (row['day'], row['key']))}


def risk_scorecard(candidates: tuple[Candidate, ...], labels: dict[str, dict], batch) -> dict:
    """Risk accuracy over every reported outcome, including late returns."""
    points = []
    for candidate in candidates:
        key = candidate.draft.signal.record.key
        label = labels.get(key)
        record = candidate.draft.signal.record
        if (candidate.estimate is None or not label or not label.get('reported')
                or record.hold.value != 'clear'):
            continue
        points.append(ValidationPoint(
            key, record.region, record.day,
            candidate.estimate, float(label['observed']), True))
    identity = Adjustment('当班分数', (), batch.replay.adjustment.radius, 0,
                          batch.replay.adjustment.native_scale)
    result = classification(points, identity, batch.fitted.baseline, .5)
    late_points = [point for point in points if labels[point.key].get('late_report')]
    result['late_reported_points'] = len(late_points)
    result['unreported_excluded'] = sum(
        1 for candidate in candidates
        if labels.get(candidate.draft.signal.record.key, {}).get('unreported')
    )
    return result


def same_dispatch_conditions(baseline: Scenario, candidate: Scenario) -> dict:
    fields = ('budget', 'reserve', 'start', 'stop', 'region')
    matching = {name: getattr(baseline, name) == getattr(candidate, name) for name in fields}
    return {
        'same_capacity': matching['budget'] and matching['reserve'],
        'same_security_window': matching['start'] and matching['stop'],
        'same_region': matching['region'],
        'identical_conditions': all(matching.values()),
        'matching_fields': matching,
    }


def adoption_gate(baseline_score: dict | int | None = None,
                  candidate_score: dict | int | None = None,
                  baseline_schedule=None, candidate_schedule=None,
                  baseline_scenario: Scenario | None = None,
                  candidate_scenario: Scenario | None = None,
                  *, protected_keys: tuple[str, ...] | None = None,
                  **kwargs) -> dict:
    if (baseline_schedule is None or candidate_schedule is None
            or isinstance(baseline_score, (int, float))
            or isinstance(candidate_score, (int, float))
            or kwargs.get('baseline_count') is not None):
        return adoption_decision(
            baseline_score, candidate_score,
            protected_keys=protected_keys or (),
            same_capacity=kwargs.pop('same_capacity', True),
            same_security_window=kwargs.pop('same_security_window', True),
            **kwargs,
        )
    conditions = same_dispatch_conditions(baseline_scenario, candidate_scenario)
    if protected_keys is None:
        protected_keys = earliest_closeout_keys(baseline_schedule)
    candidate_rows = _booking_rows(candidate_schedule)
    baseline_rows = _booking_rows(baseline_schedule)
    displaced_earliest = sorted(
        key for key in protected_keys
        if key not in candidate_rows or candidate_rows[key].state != Disposition.BOOKED
    )
    displaced_original = sorted(
        key for key, row in baseline_rows.items() if row.state == Disposition.BOOKED
        if key not in candidate_rows or candidate_rows[key].state != Disposition.BOOKED
    )
    delta = candidate_score['covered_confirmed_missed_pieces'] - baseline_score['covered_confirmed_missed_pieces']
    case_delta = candidate_score['covered_confirmed_missed_cases'] - baseline_score['covered_confirmed_missed_cases']
    increase = delta > 0
    earliest_retained = not displaced_earliest
    reasons = []
    if not conditions['identical_conditions']:
        reasons.append('两种排法必须使用相同片区、车位预算、预留和安检窗口')
    if not increase:
        reasons.append('回放覆盖的已确认误机行李件数没有增加')
    if displaced_earliest:
        reasons.append('新排法会挤掉原排法中截关最早的单据：' + '、'.join(displaced_earliest))
    adopt = conditions['identical_conditions'] and increase and earliest_retained
    if adopt:
        reasons.append(f'相同车位与安检窗口下，已确认误机覆盖增加 {delta} 件，且最早截关单未被挤掉')
    basis_note = '风险仅使用当班可见特征；迟到回报只进入计分；未回报单据单独统计，不计作无误机。'
    activation_basis = '；'.join([*reasons, basis_note])
    return {
        'adopt': adopt, 'enabled': adopt, 'enable': adopt, 'should_enable': adopt,
        'can_enable': adopt, 'eligible': adopt, 'approved': adopt,
        'decision': 'enable' if adopt else 'hold',
        'verdict': '启用新排法' if adopt else '暂不启用新排法',
        'reason': '；'.join(reasons),
        'activation_basis': activation_basis,
        'enablement_basis': activation_basis,
        'basis': basis_note,
        'basis_details': reasons,
        'reasons': reasons,
        'recommended': 'risk_guard' if adopt else 'early_run',
        'metric': 'covered_confirmed_missed_pieces',
        'baseline_count': baseline_score['covered_confirmed_missed_pieces'],
        'candidate_count': candidate_score['covered_confirmed_missed_pieces'],
        'baseline_covered_confirmed_missed': baseline_score['covered_confirmed_missed_pieces'],
        'candidate_covered_confirmed_missed': candidate_score['covered_confirmed_missed_pieces'],
        'covered_confirmed_missed_delta': delta,
        'covered_confirmed_missed_cases_delta': case_delta,
        'increase': increase,
        'same_capacity': conditions['same_capacity'],
        'same_security_window': conditions['same_security_window'],
        'identical_conditions': conditions['identical_conditions'],
        'protected_earliest_keys': list(protected_keys),
        'earliest_retained': earliest_retained,
        'protection_satisfied': earliest_retained,
        'guard_passed': earliest_retained,
        'displaced_earliest': displaced_earliest,
        'displaced_original': displaced_original,
    }


def adoption_decision(baseline_score: dict | None = None,
                      candidate_score: dict | None = None,
                      baseline_schedule=None, candidate_schedule=None,
                      baseline_scenario: Scenario | None = None,
                      candidate_scenario: Scenario | None = None,
                      *, baseline_count: int | None = None,
                      candidate_count: int | None = None,
                      covered_delta: int | None = None,
                      delta: int | None = None,
                      protected_keys: tuple[str, ...] | list[str] = (),
                      displaced_earliest: tuple[str, ...] | list[str] = (),
                      same_capacity: bool = True,
                      same_security_window: bool = True,
                      identical_conditions: bool | None = None,
                      **_ignored) -> dict:
    """Small permissive gate for callers that already computed coverage counts."""
    if isinstance(baseline_score,(int,float)) and baseline_count is None:
        baseline_count = int(baseline_score)
        baseline_score = None
    if isinstance(candidate_score,(int,float)) and candidate_count is None:
        candidate_count = int(candidate_score)
        candidate_score = None
    if baseline_score is not None and baseline_count is None:
        baseline_count = baseline_score.get('covered_confirmed_missed_pieces',
                                             baseline_score.get('covered_confirmed_missed', 0))
    if candidate_score is not None and candidate_count is None:
        candidate_count = candidate_score.get('covered_confirmed_missed_pieces',
                                              candidate_score.get('covered_confirmed_missed', 0))
    baseline_count = int(baseline_count or 0)
    candidate_count = int(candidate_count or 0)
    coverage_delta = candidate_count - baseline_count if covered_delta is None and delta is None else int(
        covered_delta if covered_delta is not None else delta)
    if baseline_scenario is not None and candidate_scenario is not None:
        conditions = same_dispatch_conditions(baseline_scenario, candidate_scenario)
        same_capacity = conditions['same_capacity']
        same_security_window = conditions['same_security_window']
        identical = conditions['identical_conditions']
    else:
        identical = (same_capacity and same_security_window) if identical_conditions is None else identical_conditions
    displaced = tuple(displaced_earliest or ())
    increase = coverage_delta > 0
    earliest_retained = not displaced
    adopt = bool(identical and increase and earliest_retained)
    reasons = []
    if not identical:
        reasons.append('两种排法必须使用相同车位和安检窗口')
    if not increase:
        reasons.append('回放覆盖的已确认误机行李件数没有增加')
    if displaced:
        reasons.append('最早截关单会被挤掉：' + '、'.join(displaced))
    if adopt:
        reasons.append(f'已确认误机覆盖增加 {coverage_delta} 件，且最早截关单未被挤掉')
    basis_note = '迟到回报只用于计分；未回报单另算；特征按当班可见性冻结。'
    return {
        'adopt': adopt, 'enabled': adopt, 'enable': adopt, 'should_enable': adopt,
        'can_enable': adopt, 'eligible': adopt, 'decision': 'enable' if adopt else 'hold',
        'reason': '；'.join(reasons), 'reasons': reasons,
        'activation_basis': '；'.join([*reasons, basis_note]),
        'baseline_count': baseline_count, 'candidate_count': candidate_count,
        'covered_confirmed_missed_delta': coverage_delta, 'increase': increase,
        'identical_conditions': identical, 'same_capacity': same_capacity,
        'same_security_window': same_security_window,
        'protected_earliest_keys': list(protected_keys),
        'displaced_earliest': list(displaced), 'earliest_retained': earliest_retained,
        'basis': basis_note,
    }


def compare_policy_replay(batch, scenario: Scenario = Scenario(14),
                          windows: Windows = Windows(),
                          candidate_mode: str = 'risk_guard') -> dict:
    """Run original, pure risk and guarded-risk policies over one holdout."""
    labels = outcome_ledger(batch.report.tickets, windows)
    candidates = build_replay_candidates(batch, windows, scenario)
    risk_metrics = risk_scorecard(candidates, labels, batch)
    baseline_scenario = replace(scenario, mode='early_run')
    baseline_schedule = allocate(candidates, baseline_scenario, mode='early_run')
    baseline_score = score_schedule(baseline_schedule, candidates, labels)

    earliest_keys = earliest_closeout_keys(baseline_schedule)
    risk_scenario = replace(scenario, mode='risk_first')
    risk_schedule = allocate(candidates, risk_scenario, mode='risk_first')
    risk_score = score_schedule(risk_schedule, candidates, labels)
    risk_gate = adoption_gate(baseline_score, risk_score, baseline_schedule, risk_schedule,
                              baseline_scenario, risk_scenario, protected_keys=earliest_keys)

    guard_scenario = replace(scenario, mode=normalize_policy(candidate_mode))
    guard_schedule = allocate(candidates, guard_scenario, mode='risk_guard',
                              protected_keys=earliest_keys)
    guard_score = score_schedule(guard_schedule, candidates, labels)
    guard_gate = adoption_gate(baseline_score, guard_score, baseline_schedule, guard_schedule,
                               baseline_scenario, guard_scenario, protected_keys=earliest_keys)

    deadline_scenario = replace(scenario, mode='deadline_first')
    deadline_schedule = allocate(candidates, deadline_scenario, mode='deadline_first')
    deadline_score = score_schedule(deadline_schedule, candidates, labels)

    unreported_keys = sorted(key for key, value in labels.items()
                             if value.get('unreported') and any(c.draft.signal.record.key == key for c in candidates))
    late_keys = sorted(key for key, value in labels.items()
                       if value.get('late_report') and any(c.draft.signal.record.key == key for c in candidates))
    post_window_keys = sorted(key for key, value in labels.items()
                              if value.get('post_window_report') and any(c.draft.signal.record.key == key for c in candidates))
    recommendation = dict(guard_gate)
    return {
        'scenario': {**asdict(scenario), 'strategy': scenario.mode, 'policy': scenario.mode},
        'window': windows.bounds(),
        'risk_score': risk_metrics,
        'label_score': risk_metrics,
        'label_policy': {
            'late_reports_only_score': True,
            'unreported_count': baseline_score['unreported'],
            'unreported_keys': unreported_keys,
            'late_report_count': baseline_score['late_reports'],
            'late_report_keys': late_keys,
            'late_return_count': baseline_score['late_reports'],
            'post_window_report_count': baseline_score['post_window_reports'],
            'post_window_report_keys': post_window_keys,
        },
        'baseline_policy': 'early_run',
        'candidate_policy': 'risk_guard',
        'earliest_closeout_keys': list(earliest_keys),
        'baseline': baseline_score,
        'candidate': guard_score,
        'deadline_first': deadline_score,
        'risk_first': {**risk_score, 'adoption': risk_gate},
        'adoption': recommendation,
        'recommendation': recommendation,
        'baseline_covered_confirmed_missed': baseline_score['covered_confirmed_missed_pieces'],
        'candidate_covered_confirmed_missed': guard_score['covered_confirmed_missed_pieces'],
        'baseline_covered_confirmed_missed_cases': baseline_score['covered_confirmed_missed_cases'],
        'candidate_covered_confirmed_missed_cases': guard_score['covered_confirmed_missed_cases'],
        # Common top-level aliases used by workbench/API consumers.
        **{key: recommendation[key] for key in ('adopt', 'enabled', 'enable', 'should_enable',
                                                'reasons', 'covered_confirmed_missed_delta')},
    }


def compare_named_policies(batch, baseline: Scenario, candidate: Scenario,
                           windows: Windows = Windows()) -> dict:
    """Score the exact two scenarios/modes submitted to /api/compare."""
    labels = outcome_ledger(batch.report.tickets, windows)
    # Resource scope is shared; mode is carried by each scenario.
    candidates = build_replay_candidates(batch, windows, baseline)
    baseline_schedule = allocate(candidates, baseline)
    earliest_keys = earliest_closeout_keys(baseline_schedule)
    candidate_candidates = candidates
    if candidate.region != baseline.region:
        candidate_candidates = build_replay_candidates(batch, windows, candidate)
    protected = (earliest_keys if normalize_policy(candidate.mode) == 'risk_guard'
                 and candidate.region == baseline.region else ())
    candidate_schedule = allocate(candidate_candidates, candidate, protected_keys=protected)
    baseline_score = score_schedule(baseline_schedule, candidates, labels)
    candidate_score = score_schedule(candidate_schedule, candidate_candidates, labels)
    gate = adoption_gate(baseline_score, candidate_score, baseline_schedule, candidate_schedule,
                         baseline, candidate, protected_keys=earliest_keys)
    return {
        'baseline_mode': normalize_policy(baseline.mode),
        'candidate_mode': normalize_policy(candidate.mode),
        'baseline': baseline_score,
        'candidate': candidate_score,
        'baseline_covered_confirmed_missed': baseline_score['covered_confirmed_missed_pieces'],
        'candidate_covered_confirmed_missed': candidate_score['covered_confirmed_missed_pieces'],
        'adoption': gate,
        **{key: gate[key] for key in ('adopt', 'enabled', 'enable', 'should_enable',
                                      'reasons', 'covered_confirmed_missed_delta')},
    }


def evaluate_policy(batch, scenario: Scenario = Scenario(14),
                    windows: Windows = Windows()) -> dict:
    """Allocate one explicit policy and score it against later outcomes."""
    labels = outcome_ledger(batch.report.tickets, windows)
    candidates = build_replay_candidates(batch, windows, scenario)
    schedule = allocate(candidates, scenario)
    score = score_schedule(schedule, candidates, labels)
    return {'scenario': asdict(scenario), 'score': score,
            'items': score['items'], 'schedule_used': schedule.used}


score_policy = evaluate_policy
evaluate_dispatch = evaluate_policy
dispatch_score = evaluate_policy
build_dispatch_replay = compare_policy_replay
compare_dispatch_policies = compare_policy_replay
review_policy = compare_policy_replay
policy_replay_review = compare_policy_replay


def replay_dispatch(content: bytes, scenario: Scenario = Scenario(14),
                    windows: Windows = Windows()):
    # Local import avoids a process <-> replay_policy import cycle at module import time.
    from .process import prepare_batch
    return compare_policy_replay(prepare_batch(content, windows), scenario, windows)
