import json


def estimate_tokens(messages: list[dict]) -> int:
    """Honest, conservative text/image estimate; never count base64 as text."""
    characters = images = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            characters += len(content)
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    characters += len(str(part.get("text", "")))
                elif part.get("type") == "image_url":
                    images += 1
        images += len(message.get("images", []) or [])
        if message.get("tool_calls"):
            characters += len(json.dumps(message["tool_calls"], ensure_ascii=False))
    return max(1, (characters + 2) // 3 + len(messages) * 4 + images * 2048)
