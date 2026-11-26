from dataclasses import dataclass
from enum import StrEnum

from ..transfer_signals.contracts import Prepared
from ..settings import PLACEMENT_MODE
from .policy_names import normalize_policy


class Disposition(StrEnum):
    BOOKED = 'booked'
    WAIT = 'wait'
    MANUAL = 'manual'
    NORMAL = 'normal'
    LOCKED = 'locked'


@dataclass(frozen=True, slots=True, init=False)
class Scenario:
    budget: int
    reserve: int = 0
    region: str | None = None
    start: int = 360
    stop: int = 1005
    mode: str = PLACEMENT_MODE

    def __init__(self, budget: int, reserve: int = 0, region: str | None = None,
                 start: int = 360, stop: int = 1005, mode: str | None = None, *,
                 strategy: str | None = None, policy: str | None = None,
                 order: str | None = None, method: str | None = None,
                 placement: str | None = None, dispatch_mode: str | None = None,
                 ranking: str | None = None) -> None:
        chosen = (mode or strategy or policy or order or method or placement
                  or dispatch_mode or ranking or PLACEMENT_MODE)
        if (type(budget) is not int or type(reserve) is not int or
                not 0 <= reserve <= budget <= 10000):
            raise ValueError('预算与预留须为整数，且在 0 至 10000 之间')
        if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= 1440:
            raise ValueError('服务窗口起止不合法')
        if not isinstance(chosen, str) or not chosen.strip() or len(chosen) > 40:
            raise ValueError('排班策略名称无效')
        object.__setattr__(self, 'budget', budget)
        object.__setattr__(self, 'reserve', reserve)
        object.__setattr__(self, 'region', region)
        object.__setattr__(self, 'start', start)
        object.__setattr__(self, 'stop', stop)
        object.__setattr__(self, 'mode', normalize_policy(chosen))

    def __post_init__(self) -> None:  # pragma: no cover - init=False keeps validation in __init__
        ...

    @property
    def strategy(self) -> str:
        return self.mode

    @property
    def spendable(self) -> int:
        return self.budget - self.reserve


@dataclass(frozen=True, slots=True)
class Draft:
    signal: Prepared
    state: Disposition
    units: int
    minimum: int
    step: int
    priority: float
    duration: int
    why: str
    resource: str


@dataclass(frozen=True, slots=True)
class Candidate:
    draft: Draft
    estimate: float | None
    range: tuple[float,float] | None
    explanations: tuple[tuple[str,float],...]


@dataclass(frozen=True, slots=True)
class Booking:
    candidate: Candidate
    state: Disposition
    assigned: int
    start: int | None
    end: int | None
    why: str

    @property
    def key(self):
        return self.candidate.draft.signal.record.key


@dataclass(frozen=True, slots=True)
class Schedule:
    rows: tuple[Booking,...]
    used: int
    left: int
    protected: int
    by_region: dict[str,int]
    by_resource: dict[str,int]

    def verify(self, scenario: Scenario) -> None:
        units = sum(row.assigned for row in self.rows)
        if units != self.used or self.used+self.left+self.protected != scenario.budget:
            raise RuntimeError('派工额度与预留不守恒')
        if self.used != sum(self.by_region.values()) or self.used != sum(self.by_resource.values()):
            raise RuntimeError('去向汇总与已分派不一致')
        if len({row.key for row in self.rows}) != len(self.rows):
            raise RuntimeError('作业单据重复')
        for row in self.rows:
            if row.assigned < 0 or row.assigned > row.candidate.draft.units:
                raise RuntimeError('单条派工超过申报')
            if row.assigned != 0 and (row.state != Disposition.BOOKED or row.start is None or row.end is None):
                raise RuntimeError('已占资源缺服务窗口')
