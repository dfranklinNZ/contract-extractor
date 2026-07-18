# hello.py
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()  # copies .env values into os.environ

client = Anthropic()  # finds ANTHROPIC_API_KEY in the environment itself

message = client.messages.create(
    model="claude-haiku-4-5-20251001",   # cheapest — this is a plumbing test
    max_tokens=50,
    messages=[{"role": "user", "content": "Say hello in five words."}],
)
print(message.content[0].text)