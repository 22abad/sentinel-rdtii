#!/bin/bash
# Re-run IND/LAO/THA with gate fixes — wrapper script (background-safe)
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private
echo "=== IND $(date) ===" >> logs/hunt_IND_postfix.log
python3 main.py --economy India --from-corpus --pillar 1,3,5,9,10,12 --provider deepseek >> logs/hunt_IND_postfix.log 2>&1
echo "=== LAO $(date) ===" >> logs/hunt_LAO_postfix.log
python3 main.py --economy "Lao PDR" --from-corpus --pillar 4,5,7,8,12 --provider deepseek >> logs/hunt_LAO_postfix.log 2>&1
echo "=== THA $(date) ===" >> logs/hunt_THA_postfix.log
python3 main.py --economy Thailand --from-corpus --pillar 5,11,12 --provider deepseek >> logs/hunt_THA_postfix.log 2>&1
echo "ALL DONE $(date)" >> logs/hunt_THA_postfix.log
