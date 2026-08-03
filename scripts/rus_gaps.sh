#!/bin/bash
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private
echo "=== RUS gaps $(date) ===" >> logs/hunt_RUS_gaps.log
python3 main.py --economy "Russian Federation" --from-corpus --pillar 1,5,6,7,8,9,10,11,12 --provider deepseek >> logs/hunt_RUS_gaps.log 2>&1
echo "DONE $(date)" >> logs/hunt_RUS_gaps.log
