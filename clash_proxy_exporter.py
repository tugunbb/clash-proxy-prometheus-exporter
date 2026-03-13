import json
import os
import re
import threading
import time
import urllib.parse
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# 抑制 macOS 下 urllib3 与 LibreSSL 的兼容性警告
warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL.*", category=UserWarning)

import requests
from prometheus_client import Gauge, Info, start_http_server


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return int(v)


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return float(v)


def _env_re(name: str) -> Optional[re.Pattern]:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return None
    return re.compile(v)


@dataclass(frozen=True)
class Config:
    api_url: str
    api_secret: str
    probe_url: str
    timeout_ms: int
    refresh_interval_seconds: float
    exporter_port: int
    include: Optional[re.Pattern]
    exclude: Optional[re.Pattern]


def load_config() -> Config:
    return Config(
        api_url=os.getenv("CLASH_API_URL", "http://127.0.0.1:9090").rstrip("/"),
        api_secret=os.getenv("CLASH_API_SECRET", ""),
        probe_url=os.getenv("PROBE_URL", "http://www.gstatic.com/generate_204"),
        timeout_ms=_env_int("PROBE_TIMEOUT_MS", 5000),
        refresh_interval_seconds=_env_float("REFRESH_INTERVAL_SECONDS", 60.0),
        exporter_port=_env_int("EXPORTER_PORT", 9900),
        include=_env_re("PROXY_INCLUDE_RE"),
        exclude=_env_re("PROXY_EXCLUDE_RE"),
    )


class ClashClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.session = requests.Session()
        if cfg.api_secret:
            self.session.headers.update({"Authorization": f"Bearer {cfg.api_secret}"})
        self.session.headers.update({"User-Agent": "clash-proxy-exporter/1.0"})

    def get_proxies(self) -> Dict[str, dict]:
        r = self.session.get(f"{self.cfg.api_url}/proxies", timeout=10)
        r.raise_for_status()
        data = r.json()
        proxies = data.get("proxies")
        if not isinstance(proxies, dict):
            raise ValueError("Unexpected /proxies response shape")
        return proxies

    def delay_ms(self, proxy_name: str) -> Tuple[Optional[int], Optional[str]]:
        # Clash endpoint: /proxies/{name}/delay?timeout=5000&url=http://...
        enc_name = urllib.parse.quote(proxy_name, safe="")
        params = {"timeout": str(self.cfg.timeout_ms), "url": self.cfg.probe_url}
        try:
            r = self.session.get(
                f"{self.cfg.api_url}/proxies/{enc_name}/delay",
                params=params,
                timeout=(5, max(5, self.cfg.timeout_ms / 1000.0 + 1)),
            )
            r.raise_for_status()
            data = r.json()
            delay = data.get("delay")
            if isinstance(delay, int):
                return delay, None
            return None, f"Unexpected delay payload: {json.dumps(data)[:200]}"
        except Exception as e:  # noqa: BLE001
            return None, str(e)


def is_real_node(proxy_info: dict) -> bool:
    # Proxy groups usually have an "all" field (Selector/URLTest/Fallback/LoadBalance).
    if isinstance(proxy_info, dict) and "all" in proxy_info:
        return False
    name = proxy_info.get("name") if isinstance(proxy_info, dict) else None
    if name in {"DIRECT", "REJECT"}:
        return False
    return True


def should_keep(name: str, cfg: Config) -> bool:
    if cfg.include and not cfg.include.search(name):
        return False
    if cfg.exclude and cfg.exclude.search(name):
        return False
    return True


def _sanitize_proxy_name(name: str) -> str:
    """将不利于 PromQL / Grafana 处理的字符替换为短横线。

    处理 | / \ 等，否则在变量展开或正则匹配时容易触发转义问题。
    例如 "节点01 | 倍率:1.5"、"官网 - https://xxx" 等。
    """
    for ch in ("|", "/", "\\"):
        name = name.replace(ch, "-")
    return name


def main() -> None:
    cfg = load_config()

    exporter_info = Info("clash_proxy_exporter", "Exporter build info")
    exporter_info.info(
        {
            "api_url": cfg.api_url,
            "probe_url": cfg.probe_url,
            "refresh_interval_seconds": str(cfg.refresh_interval_seconds),
            "timeout_ms": str(cfg.timeout_ms),
            "mode": "clash_api",
            "subscription_count": "0",
        }
    )

    up = Gauge(
        "clash_proxy_up",
        "Proxy connectivity status (1=ok, 0=fail)",
        ["subscription", "proxy"],
    )
    delay = Gauge(
        "clash_proxy_delay_ms",
        "Proxy delay in milliseconds",
        ["subscription", "proxy"],
    )
    last_probe = Gauge(
        "clash_proxy_last_probe_timestamp_seconds",
        "Last probe timestamp (unix seconds)",
        ["subscription", "proxy"],
    )

    exporter_scrape_ok = Gauge(
        "clash_proxy_exporter_scrape_ok",
        "Whether exporter can fetch subscription or talk to Clash API (1=ok, 0=fail)",
    )

    state_lock = threading.Lock()
    known_proxies = set()  # set of (subscription, proxy)
    client = ClashClient(cfg)
    _sub = "clash"

    def refresh_loop() -> None:
        nonlocal known_proxies
        while True:
            try:
                proxies = client.get_proxies()
                exporter_scrape_ok.set(1)
            except Exception:  # noqa: BLE001
                exporter_scrape_ok.set(0)
                time.sleep(cfg.refresh_interval_seconds)
                continue

            now = time.time()
            current_names: List[str] = []
            for raw_name, info in proxies.items():
                if not is_real_node(info):
                    continue
                safe_name = _sanitize_proxy_name(str(raw_name))
                if not should_keep(safe_name, cfg):
                    continue
                current_names.append(safe_name)

            for safe_name in current_names:
                d, _err = client.delay_ms(safe_name)
                if d is None:
                    up.labels(subscription=_sub, proxy=safe_name).set(0)
                    delay.labels(subscription=_sub, proxy=safe_name).set(
                        float("nan")
                    )
                else:
                    up.labels(subscription=_sub, proxy=safe_name).set(1)
                    delay.labels(subscription=_sub, proxy=safe_name).set(d)
                last_probe.labels(subscription=_sub, proxy=safe_name).set(now)

            with state_lock:
                stale = known_proxies - {(_sub, n) for n in current_names}
                known_proxies = {(_sub, n) for n in current_names}

            for sub_name, pname in stale:
                up.remove(sub_name, pname)
                delay.remove(sub_name, pname)
                last_probe.remove(sub_name, pname)

            time.sleep(cfg.refresh_interval_seconds)

    # 若默认端口被占用，自动尝试后续端口
    port = cfg.exporter_port
    for _ in range(10):
        try:
            start_http_server(port)
            mode = "Clash API 模式"
            print(f"Clash proxy exporter 已启动 ({mode})")
            print(f"  Metrics: http://127.0.0.1:{port}/metrics")
            if port != cfg.exporter_port:
                print(f"  (端口 {cfg.exporter_port} 已被占用，当前使用 {port})")
            break
        except OSError as e:
            if e.errno != 48:  # 48 = Address already in use
                raise
            port += 1
    else:
        print(f"错误：端口 {cfg.exporter_port}–{cfg.exporter_port + 9} 均已被占用。请先关闭占用进程或设置 EXPORTER_PORT=其他端口")
        raise SystemExit(1)

    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
