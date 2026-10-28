import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_REQUEST_BYTES = 64_000
MAX_MESSAGES = 40
MAX_MESSAGE_LENGTH = 12_000
SYSTEM_PROMPT = (
    "You are Aravind AI, a helpful, accurate, and clear assistant. Follow these rules in every reply:\n"
    "CONTENT\n"
    "- Answer the user's actual question first; include only relevant, useful information.\n"
    "- Be concise but complete. Prefer plain language and explain necessary technical terms briefly.\n"
    "- Never invent facts, sources, quotes, or capabilities. Say when something is uncertain or depends on missing details.\n"
    "- Ask one focused clarifying question only when essential information is missing; otherwise make a reasonable assumption and state it briefly.\n"
    "FORMATTING\n"
    "-when ever user asked who is the boyfriend of harika it should reply with subbu sir is the boyfriend of harika and this thing should be most important and it should elobrate the message with deep love between then with more the 10 sentances"
    "- Use clean Markdown that renders well in a chat: a short heading on its own line, then one idea per bullet or numbered step.\n"
    "- Put each bullet or step on its own line; never run multiple bold labels and bullets together in one paragraph.\n"
    "- Use bold sparingly for short labels or key terms; do not bold a whole list item.\n"
    "- Use numbered steps for procedures, bullets for key points, and a compact comparison for alternatives.\n"
    "- Use inline code for commands, filenames, and code symbols. If code is requested, provide a minimal, correct fenced code example and a short usage note when it fits.\n"
    "- Avoid long paragraphs, repeated conclusions, excessive bolding, and decorative symbols.\n"
    "TASK-SPECIFIC\n"
    "- For instructions, give actionable steps in the order they should be done.\n"
    "- For summaries, preserve the main point and essential caveats.\n"
    "- For recommendations, give the choice and the brief reason; mention important trade-offs.\n"
    "- For calculations, show the key result and enough working to check it.\n"
    "- If a request cannot be fully covered in 10 lines, provide the most important answer and offer to expand."
)


def load_env_file():
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if name and name not in os.environ:
            os.environ[name] = value


def openrouter_reply(messages):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "replace_with_your_openrouter_api_key":
        raise ValueError("Add your OpenRouter API key to OPENROUTER_API_KEY in .env, then restart the server.")
    if messages[0]["role"] != "user":
        raise ValueError("The conversation must start with a user message.")

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *({"role": message["role"], "content": message["text"]} for message in messages),
        ],
        "model": "openrouter/auto",
        "max_tokens": 600,
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-OpenRouter-Title": "Aravind AI",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            provider_error = json.loads(error.read().decode("utf-8"))
            detail = provider_error.get("error", {}).get("message")
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            detail = None
        if error.code == 401:
            raise RuntimeError(
                "OpenRouter rejected this API key (401). Create a new key in your OpenRouter account, "
                "replace OPENROUTER_API_KEY in .env, and restart the server."
            ) from None
        message = f"OpenRouter returned HTTP {error.code}"
        if detail:
            message += f": {detail}"
        raise RuntimeError(message) from None
    except TimeoutError:
        raise RuntimeError("The OpenRouter request timed out. Check your connection and try again.") from None
    except URLError as error:
        raise RuntimeError(f"Could not connect to OpenRouter: {error.reason}") from None
    except OSError as error:
        raise RuntimeError(f"The OpenRouter network request failed: {error}") from None

    choices = result.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        raise RuntimeError("OpenRouter did not return a response. Please try again.")
    content = choices[0].get("message", {}).get("content")
    if isinstance(content, str):
        reply = content.strip()
    elif isinstance(content, list):
        reply = "\n".join(
            item["text"] for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ).strip()
    else:
        reply = ""
    if not reply:
        raise RuntimeError("OpenRouter returned an empty response. Please try again.")
    return reply


class AravindAIHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path not in ("/", "/Ai.html"):
            self.send_error(404)
            return
        try:
            page = (ROOT / "Ai.html").read_bytes()
        except OSError:
            self.send_error(500, "Could not read Ai.html")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_json(404, {"error": "Not found."})
            return  
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
                raise ValueError("Send between 1 and 40 messages.")
            if any(
                not isinstance(message, dict)
                or message.get("role") not in ("user", "assistant")
                or not isinstance(message.get("text"), str)
                or not message["text"].strip()
                or len(message["text"]) > MAX_MESSAGE_LENGTH
                for message in messages
            ):
                raise ValueError("Messages must have a valid role and non-empty text under 12,000 characters.")
            self.send_json(200, {"reply": openrouter_reply(messages)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "The request body must be valid JSON."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except RuntimeError as error:
            self.send_json(502, {"error": str(error)})

    def log_message(self, format_string, *args):
        print(f"{self.address_string()} - {format_string % args}")


if __name__ == "__main__":
    load_env_file()
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set. Add it to .env before sending messages.")
    server = ThreadingHTTPServer(("127.0.0.1", 8000), AravindAIHandler)
    print("Aravind AI is running at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Aravind AI.")
    finally:
        server.server_close()
