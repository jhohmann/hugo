import os

# Tests sollen keinen echten OpenAI-Zugang benötigen.
os.environ.setdefault("OPENAI_API_KEY", "test-key")
