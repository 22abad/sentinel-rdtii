#!/bin/bash
# IND DeepSeek re-run with gate fix — pillar P1,3,5,9,10,12
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private
echo "=== IND DeepSeek re-run $(date) ==="
echo "=== IND DeepSeek re-run $(date) ===" >> logs/hunt_IND_gatefix3.log
python3 main.py --economy India --from-corpus --pillar 1,3,5,9,10,12 --provider deepseek >> logs/hunt_IND_gatefix3.log 2>&1
echo "EXIT=$?" >> logs/hunt_IND_gatefix3.log
echo "DONE $(date)" >> logs/hunt_IND_gatefix3.log
