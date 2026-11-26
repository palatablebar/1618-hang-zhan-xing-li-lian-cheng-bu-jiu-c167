# 业务模块与回归证据

AI/ML / 传统ML · 中型

## 功能模块

| 编号 | 业务模块 | 交付内容 | 核心文件 | 测试文件 |
| --- | --- | --- | --- | --- |
| M1 | `bag_handoffs` | 验签、换版与隔离 | `src/bagconnect/bag_handoffs/contracts.py` `src/bagconnect/bag_handoffs/parsing.py` `src/bagconnect/bag_handoffs/service.py` | `tests/test_bag_handoffs.py` |
| M2 | `closeout_windows` | 按可见时点冻结样本和结果 | `src/bagconnect/closeout_windows/contracts.py` `src/bagconnect/closeout_windows/revisions.py` `src/bagconnect/closeout_windows/service.py` | `tests/test_closeout_windows.py` |
| M3 | `transfer_signals` | 形成训练与当班共用的领域特征 | `src/bagconnect/transfer_signals/contracts.py` `src/bagconnect/transfer_signals/indicators.py` `src/bagconnect/transfer_signals/service.py` | `tests/test_transfer_signals.py` |
| M4 | `missed_transfer` | 估计业务结果并输出本地归因 | `src/bagconnect/missed_transfer/contracts.py` `src/bagconnect/missed_transfer/estimator.py` `src/bagconnect/missed_transfer/service.py` | `tests/test_missed_transfer.py` |
| M5 | `gate_calibration` | 逐窗校准并与历史基线比较 | `src/bagconnect/gate_calibration/contracts.py` `src/bagconnect/gate_calibration/calibration.py` `src/bagconnect/gate_calibration/service.py` | `tests/test_gate_calibration.py` |
| M6 | `terminal_cohorts` | 识别缺测、未建档与分布变动 | `src/bagconnect/terminal_cohorts/contracts.py` `src/bagconnect/terminal_cohorts/distribution.py` `src/bagconnect/terminal_cohorts/service.py` | `tests/test_terminal_cohorts.py` |
| M7 | `cart_reservations` | 按业务规则锁定和分派资源 | `src/bagconnect/cart_reservations/contracts.py` `src/bagconnect/cart_reservations/domain.py` `src/bagconnect/cart_reservations/service.py` | `tests/test_cart_reservations.py` |
| M8 | `bag_manifest` | 按版本发布、导出、回查与对账 | `src/bagconnect/bag_manifest/contracts.py` `src/bagconnect/bag_manifest/storage.py` `src/bagconnect/bag_manifest/service.py` | `tests/test_bag_manifest.py` |

## 高风险边界

| 编号 | 可观察后果 | 处理位置 | 回归用例 |
| --- | --- | --- | --- |
| TRAP-14 | 同版互斥读数隔离后继续处理其他单据 | `src/bagconnect/closeout_windows/service.py` | `tests/test_closeout_windows.py::test_exact_resends_and_conflicts` |
| TRAP-19 | 单据锁定优先于排队和默认动作 | `src/bagconnect/cart_reservations/service.py` | `tests/test_cart_reservations.py::test_locked_cannot_book` |
| TRAP-23 | 可见日等于截止的单据属于下一个窗口 | `src/bagconnect/closeout_windows/service.py` | `tests/test_closeout_windows.py::test_at_cut_is_future` |
| TRAP-26 | 陈旧发布请求保留已生效的派工版 | `src/bagconnect/bag_manifest/service.py` | `tests/test_bag_manifest.py::test_stale_leaves_head` |
| TRAP-32 | 恒定训练轴避免除零和新偏移误放 | `src/bagconnect/transfer_signals/service.py` | `tests/test_transfer_signals.py::test_constant_axis` |
| TRAP-42 | 未来修订绝不替换前序训练证据 | `src/bagconnect/closeout_windows/service.py` | `tests/test_closeout_windows.py::test_late_revision_cannot_revise_past` |
| TRAP-43 | 回放没有正例时说明指标不可定义 | `src/bagconnect/gate_calibration/service.py` | `tests/test_gate_calibration.py::test_no_positive_average_precision` |
| TRAP-44 | 未建档片区会拒识，异常流量高时禁止发布 | `src/bagconnect/terminal_cohorts/service.py` | `tests/test_terminal_cohorts.py::test_unseen_blocks_when_majority` |
| TRAP-53 | 批中相邻样本不改变单条评分 | `src/bagconnect/missed_transfer/service.py` | `tests/test_missed_transfer.py::test_point_invariance` |
| TRAP-54 | 账簿参数变化会改变模型摘要并重算 | `src/bagconnect/missed_transfer/service.py` | `tests/test_missed_transfer.py::test_fitted_signature_tracks_source` |
