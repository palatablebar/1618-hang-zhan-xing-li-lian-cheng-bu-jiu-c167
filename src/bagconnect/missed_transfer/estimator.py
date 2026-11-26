from dataclasses import dataclass
import numpy as np

from .contracts import LearningRow, Probe


@dataclass(frozen=True)
class GateRisk:
    coefficients: np.ndarray
    station_effect: dict[str, float]
    negatives: int
    positives: int
    iterations: int

    def predict(self, probe: Probe) -> float:
        hours = inputs(probe.standard)
        result = hours @ self.coefficients + self.station_effect.get(probe.region, 0.0)
        return float(logistic(np.asarray(result)))

    def describe(self) -> dict:
        return {'coefficients': self.coefficients.tolist(), 'station_offset': self.station_effect,
                'short_connections': self.positives, 'regular_transfers': self.negatives,
                'newton_iterations': self.iterations, 'feature_terms': 8}


def inputs(row: tuple[float, ...]):
    slack, queue, passed, labels, throughput = row
    return np.array([1., slack, queue, passed, labels, throughput, min(0, slack)*max(0, queue), max(0, throughput-.2)])


def logistic(value: np.ndarray):
    return 1 / (1 + np.exp(-np.clip(value, -45, 45)))


def fit_estimator(rows: tuple[LearningRow, ...]) -> GateRisk:
    x = np.stack([inputs(row.probe.standard) for row in rows])
    y = np.array([row.outcome for row in rows])
    coefficient = np.zeros(x.shape[1])
    coefficient[0] = np.log((y.sum() + 1)/(len(y)-y.sum()+1))
    penalty = np.diag([.03,.8,.8,.8,1.2,.9,2,1.5])
    for iteration in range(25):
        fitted = logistic(x @ coefficient)
        variance = np.maximum(.00007, fitted*(1-fitted))
        step = np.linalg.solve(x.T @ (x*variance[:,None])+penalty, x.T @ (y-fitted)-penalty @ coefficient)
        coefficient += np.clip(step, -1.25, 1.25)
        if np.max(np.abs(step)) < .00001:
            break
    coefficient[1] = min(0.0, coefficient[1])
    scores = logistic(x @ coefficient)
    stations = {}
    for station in sorted({row.probe.region for row in rows}):
        index = [i for i,row in enumerate(rows) if row.probe.region == station]
        stations[station] = float(np.clip(np.sum(y[index]-scores[index])/(3+len(index)*.23), -.6, .6))
    return GateRisk(coefficient, stations, len(y)-int(y.sum()), int(y.sum()), iteration+1)
