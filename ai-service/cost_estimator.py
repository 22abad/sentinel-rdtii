"""Legacy assumption-only cost calculator; not measured benchmark evidence.

This script estimates the API costs for processing a 50-page legal document.
Use the usage and stage-timing fields emitted by ``evaluate_golden_set.py`` for
real benchmark runs. This helper remains available only for planning scenarios.

Assumptions for a 50-page legal document:
- 50 pages * ~400 words/page = 20,000 words.
- Tokens: ~25,000 tokens per document.
- Chunks: ~50 articles/clauses.
- The classifier filters these down to ~10 relevant chunks.
- The 10 relevant chunks are sent to the LLM for feature extraction.
- Each extraction prompt is ~1,000 tokens. Output is ~150 tokens.
- Total input tokens to LLM: 10 * 1,000 = 10,000 tokens.
- Total output tokens from LLM: 10 * 150 = 1,500 tokens.
"""

def estimate_cost(provider_name: str, input_tokens: int, output_tokens: int) -> float:
    # Hardcoded pricing as of May 2026 for robust offline estimation without API keys
    # Model names match the defaults in providers/gemini.py and providers/claude.py
    prices = {
        "gemini-3-flash-preview": {"in": 0.15, "out": 0.60},
        "claude-sonnet-4-5-20250929": {"in": 3.00, "out": 15.00},
        "llama-3-8b-local": {"in": 0.00, "out": 0.00},
    }
    
    if provider_name not in prices:
        return 0.0
        
    p = prices[provider_name]
    cost = (input_tokens * p["in"] / 1_000_000) + (output_tokens * p["out"] / 1_000_000)
    return cost

def run_estimation():
    print("--- Planning estimate only (not measured benchmark evidence) ---")
    
    # Using the assumptions listed above
    input_tokens = 10000
    output_tokens = 1500
    
    print(f"Assumed Input Tokens (after classification): {input_tokens:,}")
    print(f"Assumed Output Tokens (JSON mappings):       {output_tokens:,}")
    print("-" * 55)
    
    providers_to_test = ["gemini-3-flash-preview", "claude-sonnet-4-5-20250929", "llama-3-8b-local"]
    
    for provider in providers_to_test:
        cost = estimate_cost(provider, input_tokens, output_tokens)
        print(f"Provider: {provider:<20} | Estimated Cost: ${cost:.6f}")

    print("-" * 55)
    print("Do not cite these assumptions as actual cost. Run the real benchmark instead.")

if __name__ == "__main__":
    run_estimation()
