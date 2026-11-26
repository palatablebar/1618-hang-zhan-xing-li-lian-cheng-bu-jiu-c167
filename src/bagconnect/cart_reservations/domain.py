from math import ceil, sqrt

from ..transfer_signals.contracts import Prepared
from .contracts import Disposition, Draft


def interpret(resolved: Prepared, value: float, uncertainty: float) -> Draft:
    probe = resolved.record

    def block(reason: str) -> Draft:
        return Draft(resolved,Disposition.MANUAL,0,0,1,0,0,reason,'')

    def normal(reason: str) -> Draft:
        return Draft(resolved,Disposition.NORMAL,0,0,1,0,0,reason,'')

    def proposal(qty: int, priority: float, minutes: int, reason: str, resource: str,
                 *, minimum: int | None = None, unit: int = 1) -> Draft:
        return Draft(resolved,Disposition.BOOKED,qty,qty if minimum is None else minimum,
                     unit,priority,minutes,reason,resource)

    slack, distance, bags, belt, priority, transfer = resolved.raw
    onboard = max(0.0, slack - transfer)
    transport = ceil(6 + sqrt(distance) * 2.3 + bags / 3)
    if onboard < transport or probe.window < transport:
        return block('有效截关窗口不足以完成安检交接')
    if value < .46 and onboard >= 54 and belt < 72:
        return normal('行李可随普通中转车送达')
    load = max(1, ceil(bags / 5))
    urgent = value * 58 + max(0, 37-onboard) * 1.9 + priority / 12
    return proposal(load, urgent, transport, '按分拣完成时间和安检接车位预留短接运力', '安检交接')
