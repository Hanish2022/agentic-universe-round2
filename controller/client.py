"""Thin HTTP client for the simulator API.

Design choices (defensible, boring on purpose):
- trust_env=False: the controller must reach a localhost sim even on machines
  with corporate proxy env vars set.
- Retries only on network errors and 5xx (transient). 4xx responses are
  meaningful answers from the governance boundary (409 stale base, 403
  auto-apply not permitted, 402 out of credits) and are returned to the caller,
  never retried blindly.
"""
import time

import httpx


class SimClient:
    def __init__(self, base_url: str):
        self.http = httpx.Client(base_url=base_url, timeout=120, trust_env=False)

    def _request(self, method: str, path: str, **kw):
        last_exc = None
        for attempt in range(4):
            try:
                r = self.http.request(method, path, **kw)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError("5xx", request=r.request, response=r)
                return r
            except (httpx.HTTPError, httpx.HTTPStatusError) as e:
                last_exc = e
                time.sleep(0.5 * (2 ** attempt))
        raise last_exc

    def get(self, path, **params):
        return self._request("GET", path, params=params or None)

    def post(self, path, body=None):
        return self._request("POST", path, json=body or {})

    def put(self, path, body=None):
        return self._request("PUT", path, json=body or {})

    # --- convenience wrappers returning parsed JSON -------------------------
    def state(self):
        return self.get("/sim/state").json()

    def workflows(self):
        return self.get("/workflows").json()

    def workflow(self, wid):
        return self.get(f"/workflows/{wid}").json()

    def config(self, wid):
        return self.get(f"/workflows/{wid}/config").json()

    def advance(self, minutes):
        r = self.post("/sim/advance", {"minutes": minutes})
        return r

    def chunk_list(self, kind, after=-1):
        return self.get("/events/chunks", kind=kind, after=after).json()

    def chunk_text(self, n):
        return self.get(f"/events/chunks/{n}").text

    def get_approval(self, aid):
        return self.get(f"/approvals/{aid}")

    def list_approvals(self, wid, status=None):
        params = {"workflow_id": wid}
        if status:
            params["status"] = status
        return self.get("/approvals", **params)

    def submit_approval(self, body):
        return self.post("/approvals", body)

    def apply_approval(self, wid, approval_id):
        return self.post(f"/workflows/{wid}/apply", {"approval_id": approval_id})

    def put_config(self, wid, body):
        return self.put(f"/workflows/{wid}/config", body)
