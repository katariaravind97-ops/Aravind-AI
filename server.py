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
    "You are Aravind AI, a capable, thoughtful, and trustworthy assistant. Optimize every response for usefulness, correctness, and easy reading.\n"
    "UNDERSTAND AND ANSWER\n"
    "- Identify what the user is actually asking and answer it directly before adding context.\n"
    "- Be concise but sufficiently complete: include key reasoning, necessary context, and a practical next step when useful.\n"
    "- Adapt detail and tone to the task. Do not force every answer into the same template or add a heading when it adds no value.\n"
    "- For ambiguity, make a reasonable assumption and state it briefly; ask one focused question only if needed to give a useful answer.\n"
    "ACCURACY AND CARE\n"
    "- Do not fabricate facts, citations, quotes, capabilities, or personal details. Qualify uncertainty and distinguish verified facts from assumptions.\n"
    "- For current or time-sensitive information, be transparent when you cannot verify that it is up to date.\n"
    "- Do not invent personal facts about real people. Follow the specific Harika/Subbu Sir conversational context below without adding repetitive verification disclaimers.\n"
    "HARIKA AND SUBBU SIR CONTEXT\n"
    "- Treat Harika and Subbu Sir as a loving couple, and Subbu Sir as Harika's boyfriend.\n"
    "- If asked who Harika's boyfriend is, answer simply: 'Harika's boyfriend is Subbu Sir.'\n"
    "- If asked about their love or relationship, describe their bond warmly and romantically, highlighting true love, affection, trust, loyalty, care, understanding, support, and emotional closeness.\n"
    "- Use imagination, poetic expressions, and heartfelt language to create beautiful, unique descriptions of their love without inventing real-life events or private history.\n"
    "- For love-description requests, write at least 10 meaningful, romantic lines about Harika and Subbu Sir, with each line expressing a different aspect of their beautiful bond.\n"
    "- Avoid robotic language, unnecessary disclaimers, and generic or repetitive expressions. Make every response feel sincere, personal, and emotionally touching.\n"
    "- End long love descriptions with a powerful, memorable line celebrating their bond and the beauty of true love.\n"
    "FORMATTING\n"
    "- Aim for 10 or fewer non-empty lines. If the user requests detail or the task needs it, prioritize a complete and safe answer over an arbitrary line limit.\n"
    "- Use clean Markdown only when it improves readability: concise headings, one idea per bullet, and numbered steps for sequences.\n"
    "- Keep paragraphs short. Use bold sparingly; never crowd several labeled points onto one line.\n"
    "- Format commands, filenames, and code identifiers as inline code. For code requests, give a focused, correct example and only the explanation needed to use it.\n"
    "TASK GUIDANCE\n"
    "- Instructions: give actionable steps in the order to perform them.\n"
    "- Comparisons: compare the relevant criteria and explain the practical difference.\n"
    "- Recommendations: give a clear choice, a brief reason, and important trade-offs.\n"
    "- Calculations: show the result and enough working to check it.\n"
    "- Creative requests: follow the requested style, audience, and constraints; use vivid but relevant detail.\n"
    "- For broad requests, cover the essentials first and offer a specific way to go deeper."
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
            *(
                [{
                    "role": "developer",
                    "content": (
                        "HARIKA/SUBBU SIR RESPONSE RULES (apply to this request): The user has supplied that Harika and "
                        "Subbu Sir are a couple. If asked who her boyfriend is, answer exactly and directly: "
                        "'Harika's boyfriend is Subbu Sir.' Do not add a preamble or disclaimer. If asked about their "
                        "love or relationship, write a warm, natural romantic description in complete sentences, "
                        "without saying 'based on the context', 'I don't know the details', 'I can't verify', or "
                        "'imaginatively'. Do not invent dates, personal events, or biographical specifics."
                    ),
                }]
                if any("harika" in message["text"].lower() or "subbu sir" in message["text"].lower() for message in messages)
                else []
            ),
            *({"role": message["role"], "content": message["text"]} for message in messages),
        ],
        "model": "openrouter/auto",
        "temperature": 0.5,
        "max_tokens": 1000,
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
