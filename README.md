# 航站行李联程补救

行李中转席位员每日核对联程转运单。根据截关、航站跨度和现场拥堵估计接驳风险，分配优先转运位并保留安检交接。必须保留分拣交接，车位优先留给截关提前量最小的合规行李。
内置数据是模拟业务单据，带历史结果、迟到回报、失校与缺测等情况，供本地复盘。

## 启动与跑一班

```sh
docker compose up --build -d --wait
curl -fsS http://127.0.0.1:19287/health
docker compose exec -T app python -m bagconnect.cli validate
docker compose exec -T app python -m bagconnect.cli preview --budget 14 --reserve 1
docker compose exec -T app python -m bagconnect.cli replay
docker compose exec -T app pytest -q -p no:cacheprovider
```

打开 [工作台](http://127.0.0.1:19287/)，可以调预算、选片区、看单据与近窗回放。 [接口说明](http://127.0.0.1:19287/docs)由 OpenAPI 生成，可离线获取 `/openapi.json`。
查询 `/api/decisions?limit=5` 可快速查看当班处置，`/api/replay` 返回近窗实测对照，`/api/compare` 同时回看两个方案的处置变化和预计暴露。
`POST /api/scenario` 接收 `budget`、`reserve`、`region`、`start`、`stop`。在 `POST /api/compare` 中将两份参数分别放进 `baseline`、`proposal`。发布时把预览的摘要、版号与当时参数交给 `/api/publish`。

通过 `SOURCE_FILE` 指定自备 CSV，在隔离环境中使用 `DISPATCH_STORE` 指向独立归档目录。
`docker compose down` 停止服务，已发布记录保存在 Compose 的归档卷中。

[数据和模型契约](docs/SPEC.md) · [操作与处置流程](docs/OPERATIONS.md) · [回归索引](docs/DEPTH.md)
