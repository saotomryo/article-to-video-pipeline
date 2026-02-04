from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class VoiceVoxClient:
    base_url: str

    def audio_query(self, text: str, speaker: int) -> dict:
        qs = urlencode({"text": text, "speaker": str(speaker)})
        url = f"{self.base_url.rstrip('/')}/audio_query?{qs}"
        req = Request(url, method="POST")
        with urlopen(req) as resp:
            data = resp.read().decode("utf-8")
        return json.loads(data)

    def synthesis(self, query: dict, speaker: int) -> bytes:
        qs = urlencode({"speaker": str(speaker)})
        url = f"{self.base_url.rstrip('/')}/synthesis?{qs}"
        body = json.dumps(query, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        with urlopen(req) as resp:
            return resp.read()

