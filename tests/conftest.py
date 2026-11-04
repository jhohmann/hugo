import os
import sys

# Tests sollen keinen echten OpenAI-Zugang benötigen.
os.environ.setdefault("OPENAI_API_KEY", "test-key")

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "backend"),
)
