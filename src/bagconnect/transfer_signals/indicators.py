from math import sqrt


def derive(values: tuple[float, ...]) -> tuple[float, ...]:
    """从联程转运单原始读数生成五个模型轴。"""
    slack, distance, bags, belt, priority, transfer = values
    walk_time = 2.1 * sqrt(distance)
    congestion = max(0.0, belt - 45.0) * (1 + bags / 42)
    runway = slack - transfer - walk_time
    tagged = min(100.0, priority) * sqrt(bags) / 12
    gate_throughput = bags / max(8.0, slack)
    return runway, congestion, transfer * (1 + distance / 110), tagged, gate_throughput
