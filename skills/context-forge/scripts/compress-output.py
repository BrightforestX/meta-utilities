#!/usr/bin/env python3
"""
Context Forge - Token-Aware Output Compression Helper

Lightweight, portable compressor for tool outputs, research reports, logs before LLM context.
Targets token budgets (tiktoken optional) + char heuristics. Enhances deep-research and agent pipelines.
Self-dogfoods in meta-utilities for lower token use in Grok/Cursor sessions.

Usage:
    some_command | python $META_UTILITIES_HOME/skills/context-forge/scripts/compress-output.py --max-tokens 4000 --stats
    python .../compress-output.py --file report.md --level balanced --max-tokens 2000
    Env: COMPRESS_MAX_TOKENS, CONTEXT_HOME
"""

import argparse
import sys
import re
import os
from pathlib import Path

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens using tiktoken if available, else ~4 chars/token fallback."""
    if TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.get_encoding(model)
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, len(text) // 4)


def compress_text(text: str, level: str = "balanced", max_tokens: int | None = None) -> tuple[str, float, int, int]:
    """Apply heuristics with optional token budget. Returns (compressed, char_ratio, orig_tokens, comp_tokens)."""
    original_len = len(text)
    original_tokens = count_tokens(text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) < 3:
        sentences = text.splitlines() or [text]

    if level == "aggressive":
        text = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*', '[TIME]', text)
        text = re.sub(r'(?m)^(INFO|DEBUG|WARN|ERROR|TRACE)\s+', '', text)
        text = re.sub(r'(?m)^\s+at .+?\n', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        if len(sentences) > 6:
            kept = sentences[:2] + [s for s in sentences[2:-1] if s.strip().startswith(('#', '##', '```', '-'))] + sentences[-1:]
            text = ' '.join(kept)
    elif level == "balanced":
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {3,}', '  ', text)
        lines = text.splitlines()
        deduped = []
        prev = None
        count = 0
        for line in lines:
            if line == prev:
                count += 1
            else:
                if count > 2:
                    deduped.append(f"... (repeated {count} times)")
                deduped.append(line)
                prev = line
                count = 1
        if count > 2:
            deduped.append(f"... (repeated {count} times)")
        text = '\n'.join(deduped)
        if max_tokens and original_tokens > max_tokens:
            keep_first = max(1, int(len(sentences) * 0.6))
            keep_last = max(1, int(len(sentences) * 0.2))
            text = ' '.join(sentences[:keep_first] + sentences[-keep_last:])

    text = text.strip()
    char_ratio = len(text) / original_len if original_len > 0 else 1.0
    compressed_tokens = count_tokens(text)
    return text, char_ratio, original_tokens, compressed_tokens


def main():
    parser = argparse.ArgumentParser(description="Token-aware compressor for AI context (tiktoken optional)")
    parser.add_argument("--file", "-f", help="File to compress instead of stdin")
    parser.add_argument("--level", "-l", choices=["conservative", "balanced", "aggressive"],
                        default="balanced", help="Compression level")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="Target max tokens (uses tiktoken or approx); trims for budget")
    parser.add_argument("--stats", action="store_true", help="Show token + char stats")
    args = parser.parse_args()

    max_tokens = args.max_tokens or int(os.environ.get("COMPRESS_MAX_TOKENS", "0")) or None

    if args.file:
        content = Path(args.file).read_text(encoding="utf-8", errors="ignore")
    else:
        content = sys.stdin.read()

    compressed, char_ratio, orig_toks, comp_toks = compress_text(content, args.level, max_tokens)

    if args.stats:
        saved_chars = (1 - char_ratio) * 100
        saved_toks = ((orig_toks - comp_toks) / orig_toks * 100) if orig_toks > 0 else 0
        print(f"--- Compression Stats ({args.level}) ---", file=sys.stderr)
        print(f"Original: {len(content):,} chars, {orig_toks:,} tokens", file=sys.stderr)
        print(f"Compressed: {len(compressed):,} chars, {comp_toks:,} tokens", file=sys.stderr)
        print(f"Saved: {saved_chars:.1f}% chars, {saved_toks:.1f}% tokens", file=sys.stderr)
        if TIKTOKEN_AVAILABLE:
            print("Tokenizer: tiktoken cl100k_base", file=sys.stderr)
        else:
            print("Tokenizer: fallback (~4 chars/token)", file=sys.stderr)
        print("--- End Stats ---", file=sys.stderr)

    print(compressed)


if __name__ == "__main__":
    main()