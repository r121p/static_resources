#!/usr/bin/env python3
"""Generate cost graph for LLM API usage over conversation turns.

This models TRUE quadratic growth where:
- Each message sends ALL previous conversation history as input
- Input size grows with each message
- Therefore each subsequent message costs MORE than the previous
"""

import matplotlib.pyplot as plt
import numpy as np

# Pricing configuration
INPUT_PRICE_PER_M = 1.40  # $1.40 per million input tokens (no cache)
OUTPUT_PRICE_PER_M = 4.40  # $4.40 per million output tokens
CACHE_READ_PRICE_PER_M = 0.26  # $0.26 per million cached tokens

# Token counts
SYSTEM_PROMPT_TOKENS = 20000  # 20k tokens
USER_PROMPT_TOKENS = 1000  # 1k tokens per user message
LLM_OUTPUT_TOKENS = 20000  # 20k tokens per LLM output

# Calculate costs per token
input_cost_per_token = INPUT_PRICE_PER_M / 1_000_000
output_cost_per_token = OUTPUT_PRICE_PER_M / 1_000_000
cache_read_cost_per_token = CACHE_READ_PRICE_PER_M / 1_000_000

# Calculate costs for NO CACHE scenario
message_counts = np.arange(0, 11)  # 0 to 10 messages
individual_costs_no_cache = []
cumulative_costs_no_cache = []

running_total = 0

for n in message_counts:
    if n == 0:
        individual_costs_no_cache.append(0)
        cumulative_costs_no_cache.append(0)
        continue
    
    # Input tokens for message n (same as before)
    input_tokens = (SYSTEM_PROMPT_TOKENS +
                   (n * USER_PROMPT_TOKENS) +
                   ((n - 1) * LLM_OUTPUT_TOKENS))
    
    output_tokens = LLM_OUTPUT_TOKENS
    
    # Cost without cache
    message_cost = (input_tokens * input_cost_per_token +
                   output_tokens * output_cost_per_token)
    individual_costs_no_cache.append(message_cost)
    
    running_total += message_cost
    cumulative_costs_no_cache.append(running_total)

# Calculate costs WITH CACHE
# With cache: System prompt and previous conversation are cached
# Only NEW user input is charged at full price
individual_costs_with_cache = []
cumulative_costs_with_cache = []

running_total_cache = 0

for n in message_counts:
    if n == 0:
        individual_costs_with_cache.append(0)
        cumulative_costs_with_cache.append(0)
        continue
    
    # Tokens that can be cached (previous context)
    cached_tokens = SYSTEM_PROMPT_TOKENS + ((n - 1) * USER_PROMPT_TOKENS) + ((n - 1) * LLM_OUTPUT_TOKENS)
    
    # New tokens that must be processed at full price
    new_input_tokens = USER_PROMPT_TOKENS  # Just the new user message
    output_tokens = LLM_OUTPUT_TOKENS
    
    # Cost with cache: cache read price for cached tokens, full price for new
    message_cost = (cached_tokens * cache_read_cost_per_token +  # Cheap cache read
                   new_input_tokens * input_cost_per_token +     # Full price for new
                   output_tokens * output_cost_per_token)        # Output always full price
    
    individual_costs_with_cache.append(message_cost)
    running_total_cache += message_cost
    cumulative_costs_with_cache.append(running_total_cache)

# Create the plot with cache comparison
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Plot 1: Cumulative Cost Comparison
ax1.plot(message_counts[1:], cumulative_costs_no_cache[1:], 'r-', linewidth=3, marker='o', markersize=8, label='No Cache')
ax1.fill_between(message_counts[1:], cumulative_costs_no_cache[1:], alpha=0.2, color='red')

ax1.plot(message_counts[1:], cumulative_costs_with_cache[1:], 'g-', linewidth=3, marker='s', markersize=8, label='With Cache')
ax1.fill_between(message_counts[1:], cumulative_costs_with_cache[1:], alpha=0.2, color='green')

# Add annotations for key savings
for i in [5, 10]:
    savings = cumulative_costs_no_cache[i] - cumulative_costs_with_cache[i]
    ax1.annotate(f'Save ${savings:.2f}',
                xy=(i, cumulative_costs_no_cache[i]),
                xytext=(10, 10),
                textcoords='offset points',
                fontsize=9,
                color='green',
                fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='green'))

ax1.set_xlabel('Number of Messages', fontsize=12, fontweight='bold')
ax1.set_ylabel('Cumulative Cost ($)', fontsize=12, fontweight='bold')
ax1.set_title('Cumulative Cost: Cache vs No Cache\n(Green = With Cache)',
              fontsize=13, fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0.5, 10.5)
ax1.legend(fontsize=11)

# Plot 2: Cost per Message Comparison
x = message_counts[1:]
width = 0.35

bars1 = ax2.bar(x - width/2, individual_costs_no_cache[1:], width, label='No Cache', color='coral', edgecolor='darkred')
bars2 = ax2.bar(x + width/2, individual_costs_with_cache[1:], width, label='With Cache', color='lightgreen', edgecolor='darkgreen')

ax2.set_xlabel('Message Number', fontsize=12, fontweight='bold')
ax2.set_ylabel('Cost of This Message ($)', fontsize=12, fontweight='bold')
ax2.set_title('Per-Message Cost: Cache Saves Money!\n(Cache read = $0.26/M vs $1.40/M)',
              fontsize=13, fontweight='bold')
ax2.grid(True, alpha=0.3, axis='y')
ax2.legend(fontsize=11)

plt.tight_layout()
plt.savefig('imgs/llm_cost_accumulation.png', dpi=150, bbox_inches='tight')
plt.savefig('imgs/llm_cost_accumulation.svg', format='svg', bbox_inches='tight')
print("Graph saved to imgs/llm_cost_accumulation.png and .svg")

# Print cost breakdown comparison
print("\nCost breakdown comparison:")
print("Msg | No Cache   | With Cache | Savings    | Input Tokens")
print("----|------------|------------|------------|-------------")
for i in range(1, 11):
    input_tok = SYSTEM_PROMPT_TOKENS + (i * USER_PROMPT_TOKENS) + ((n - 1) * LLM_OUTPUT_TOKENS) if i > 0 else SYSTEM_PROMPT_TOKENS
    savings = cumulative_costs_no_cache[i] - cumulative_costs_with_cache[i]
    print(f" {i:2d} | ${cumulative_costs_no_cache[i]:8.2f} | ${cumulative_costs_with_cache[i]:8.2f} | ${savings:8.2f} | {input_tok:11,}")

print(f"\nTotal savings after 10 messages: ${cumulative_costs_no_cache[10] - cumulative_costs_with_cache[10]:.2f}")
