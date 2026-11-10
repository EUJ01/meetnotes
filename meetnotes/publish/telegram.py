"""Post update files to Telegram with a bot (Bot API, standard library only). The bot must be an admin of each
channel, or a member of each group. A changed file is replaced in place when the bot posted it."""
import json
import socket
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from meetnotes.publish import PublishError

API = "https://api.telegram.org"
HINTS = {
    "chat not found": "check the chat id, and add the bot to the chat (as an admin for a channel)",
    "unauthorized": "the bot token is wrong",
    "not enough rights": "make the bot an admin of the channel, with the right to post",
}


def _multipart(fields, files):
    boundary = uuid.uuid4().hex
    out = []
    for name, value in fields.items():
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, path in files.items():
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{Path(path).name}"\r\n'
                   'Content-Type: text/markdown\r\n\r\n'.encode() + Path(path).read_bytes() + b"\r\n")
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


class Telegram:
    name = "telegram"

    def __init__(self, token, chats, api=API, opener=urllib.request.urlopen):
        self.token, self.chats, self.api, self.opener = token, {k: str(v) for k, v in chats.items()}, api, opener

    def wants(self, project):
        return project in self.chats

    def call(self, method, fields=None, files=None):
        url = f"{self.api}/bot{self.token}/{method}"
        if files:
            data, ctype = _multipart(fields or {}, files)
        else:
            data, ctype = json.dumps(fields or {}).encode(), "application/json"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype})
        try:
            with self.opener(req, timeout=60) as r:
                body = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except ValueError:
                raise PublishError(f"Telegram {method}: HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as e:
            raise PublishError(f"cannot reach Telegram: {getattr(e, 'reason', e)}")
        if not body.get("ok"):
            desc = body.get("description", "unknown error")
            hint = next((h for k, h in HINTS.items() if k in desc.lower()), "")
            raise PublishError(f"Telegram {method}: {desc}" + (f" ({hint})" if hint else ""))
        return body["result"]

    def send(self, path, project, date, previous):
        """Return (message id, what was done)."""
        chat, caption = self.chats[project], f"{project} update {date}"  # captions are limited to 1024 characters
        if previous:
            media = {"type": "document", "media": "attach://doc", "caption": f"{caption} (revised)"}
            try:
                self.call("editMessageMedia", {"chat_id": chat, "message_id": previous, "media": json.dumps(media)},
                          {"doc": path})
                return previous, "replaced in place"
            except PublishError as e:
                if "not modified" in str(e):
                    return previous, "unchanged on Telegram"
            caption += " (revised)"
        msg = self.call("sendDocument", {"chat_id": chat, "caption": caption}, {"document": path})
        return str(msg["message_id"]), "posted a revised copy of" if previous else "posted"

    def list_chats(self):
        """Chats in the bot's recent updates (Telegram keeps them about 24 hours; fails while a webhook is set)."""
        seen = {}
        for u in self.call("getUpdates"):
            for key in ("message", "channel_post", "edited_message", "edited_channel_post", "my_chat_member"):
                chat = (u.get(key) or {}).get("chat")
                if chat:
                    seen[str(chat["id"])] = (chat.get("type", "?"), chat.get("title") or chat.get("username") or "")
        return seen
