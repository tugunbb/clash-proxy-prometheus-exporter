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

## 如何使用

- 采集器要配合prometheus和grafana使用，并且一个订阅要独占一个clash API
- 首先把订阅到配置文件下载到本地，可以先把订阅url导入到Flclash中，然后在Flclash导出，省去自己转换格式到步骤
- 在订阅配置文件中设置port、socks-port、redir-port、mixed-port，这四个有的订阅会缺少一两个，只设置订阅中有的就行了，保证端口可用即可
- 然后在配置文件中设置external-controller为：127.0.0.1:9091（端口换成一个可用的即可）
- 接着运行clash API

```bash
mihomo -d “配置文件的目录”          #（看系统而定，这里展示macOS系统）
```

- 然后打开另一个bash，把采集器运行起来

```bash
EXPORTER_PORT=9900 CLASH_API_URL=http://127.0.0.1:9091 python3 clash_proxy_export.py
#如果配置问价中有secret参数，这里要加上CLASH_API_SECRET=“配置文件里的secret参数值”
```

- 然后在浏览器访问127.0.0.1:9900，如果正常出现节点信息，则采集器运行成功
- 接着修改prometheus配置文件

```bash
vim /opt/homebrew/etc/prometheus.yml     #（看系统而定，这里展示macOS系统）
#直接换行添加
  - job_name: clash_proxy_exporter
    static_configs:
      - targets: ["127.0.0.1:9901"]   #海豚湾 clashapi：9091，采集器：9901
        labels:
          subscription: 'hitun'
      - targets: ["127.0.0.1:9902"]   #最萌云 clashapi: 9092, 采集器：9902
        labels:
          subscription: 'cutecloud'
      .
      .
      .
      .
```

- 修改完成后访问浏览器访问prometheus：127.0.0.1:9090，观察prometheus获取数据是否正常，target health中clash_proxy_exporter的每一个labels是否state为up
- 接着打开grafana，浏览器访问127.0.0.1:3000

```bash
登陆帐号密码均为admin
登陆后点击Connections
选择Data sources
选择add new data source
选择prometheus然后在connection栏中填入prometheus的运行url
添加完数据源后选择Dashboards，点击new，新建一个dashboard，Add visualization
数据源选择prometheus
然后点击back to dashboard
点击右上角Settings，选择Variables，添加一个变量
General中Name填入subscription
Query options中选择data source为prometheus，Query type为Label values，Label*选择subcription，Metric选择clash_proxy_delay_ms，然后点击右上角Save dashboard保存

点击面板右上角三个点，选择Edit
在Queries中Metric选择clash_proxy_delay_ms，Label filters填入subscription=$subscription
然后展开下方Options
Legend填入{{proxy}}，然后点击Run queries
可以在右边面板设置中，Standard options一栏中Unit选择Time，选择milliseconds(ms)
最后点击右上角保存即可，到这里延迟面板就完成了

回到dashboard中，点击Add，选择Visualization
在Queries中Metric选择clash_proxy_up，Label filters填入subscription=$subscription
然后展开下方Options
Legend填入{{proxy}}，然后点击Run queries
在右侧选择state timeline面板
在右侧Thresholds栏删掉已有的指标，选择Add threshold，填入0.5，颜色选择绿色，Base的颜色选择红色，下方Thresholds mode选择Absolute，因为采集器采集为通会返回1，不通为0，所以这样设置大于0.5会显示绿色，即为节点通的颜色表示，然后点击右上角保存，到这里联通性面板也完成了
```
## License

MIT
