"""Inject network faults into RabbitMQ / pulsar-relay / Galaxy via toxiproxy.

The toxiproxy admin API is at http://localhost:8474 by default. Each
``ToxiproxyControl`` instance targets one named proxy (e.g. ``rabbitmq``)
and exposes the operations the resilience scenarios actually need.
"""
import requests

ADMIN = "http://localhost:8474"


class ToxiproxyControl:
    def __init__(self, name, admin=ADMIN):
        self.name = name
        self.admin = admin

    def _proxy_url(self):
        return f"{self.admin}/proxies/{self.name}"

    def _toxics_url(self):
        return f"{self._proxy_url()}/toxics"

    # connectivity ------------------------------------------------------------

    def disable(self):
        r = requests.post(self._proxy_url(), json={"enabled": False}, timeout=5)
        r.raise_for_status()

    def enable(self):
        r = requests.post(self._proxy_url(), json={"enabled": True}, timeout=5)
        r.raise_for_status()

    # toxics ------------------------------------------------------------------

    def add_latency(self, ms, jitter=0):
        return self._add_toxic("latency", {"latency": ms, "jitter": jitter})

    def add_blackhole(self):
        # A "timeout" toxic with timeout=0 acts as a permanent blackhole on
        # downstream traffic. Pair with disable() for full bidirectional drop.
        return self._add_toxic("timeout", {"timeout": 0}, stream="downstream")

    def reset_peer(self):
        return self._add_toxic("reset_peer", {"timeout": 0})

    def remove_all_toxics(self):
        r = requests.get(self._toxics_url(), timeout=5)
        r.raise_for_status()
        for toxic in r.json():
            requests.delete(f"{self._toxics_url()}/{toxic['name']}", timeout=5)

    def _add_toxic(self, ttype, attributes, stream="downstream"):
        body = {"type": ttype, "stream": stream, "attributes": attributes}
        r = requests.post(self._toxics_url(), json=body, timeout=5)
        r.raise_for_status()
        return r.json()
