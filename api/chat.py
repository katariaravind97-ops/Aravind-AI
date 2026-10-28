import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import MAX_MESSAGE_LENGTH, MAX_MESSAGES, MAX_REQUEST_BYTES, openrouter_reply


class handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Invalid request length."})
            return

        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.send_json(413, {"error": "The request is empty or too large."})
            return

        try:
            payload = json.loads(self.rfile.read(length))
            messages = payload.get("messages") if isinstance(payload, dict) else None
            if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES:
                raise ValueError(f"Send between 1 and {MAX_MESSAGES} messages.")
            if any(
                not isinstance(message, dict)
                or message.get("role") not in ("user", "assistant")
                or not isinstance(message.get("text"), str)
                or not message["text"].strip()
                or len(message["text"]) > MAX_MESSAGE_LENGTH
                for message in messages
            ):
                raise ValueError(
                    f"Messages must have a valid role and non-empty text under {MAX_MESSAGE_LENGTH:,} characters."
                )
            self.send_json(200, {"reply": openrouter_reply(messages)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "The request body must be valid JSON."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except RuntimeError as error:
            self.send_json(502, {"error": str(error)})

    def do_GET(self):
        self.send_json(405, {"error": "Use POST to send a chat message."})

    def log_message(self, format_string, *args):
        print(f"{self.address_string()} - {format_string % args}")
