# Clash Proxy Exporter

基于 Clash API 的 Prometheus Exporter，用于采集代理节点连通状态与延迟指标。

## 功能

- 从 Clash API 获取代理列表，对每个节点调用延迟探测接口
- 导出 Prometheus 指标：`clash_proxy_up`、`clash_proxy_delay_ms`、`clash_proxy_last_probe_timestamp_seconds`
- 支持通过环境变量配置 API 地址、探测 URL、超时、过滤正则等

## 环境要求

- Python 3.7+
- 运行中的 Clash（并开启 External Controller / API）

## 安装与运行

```bash
pip install -r requirements.txt
python clash_proxy_exporter.py
```

默认在 `http://127.0.0.1:9900/metrics` 暴露指标。

## 配置（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLASH_API_URL` | `http://127.0.0.1:9090` | Clash API 地址 |
| `CLASH_API_SECRET` | （空） | API 认证密钥（若需要） |
| `PROBE_URL` | `http://www.gstatic.com/generate_204` | 延迟探测 URL |
| `PROBE_TIMEOUT_MS` | `5000` | 探测超时（毫秒） |
| `REFRESH_INTERVAL_SECONDS` | `60` | 刷新间隔（秒） |
| `EXPORTER_PORT` | `9900` | Exporter 监听端口 |
| `PROXY_INCLUDE_RE` | （空） | 仅采集匹配的节点名（正则） |
| `PROXY_EXCLUDE_RE` | （空） | 排除匹配的节点名（正则） |

## License

MIT
