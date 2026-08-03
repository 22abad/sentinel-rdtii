#!/bin/bash
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private
echo "=== IDN gaps $(date) ===" >> logs/hunt_IDN_gaps2.log
python3 main.py --economy Indonesia --from-corpus --pillar 2,3,4,5,8,10,11,12 --provider deepseek >> logs/hunt_IDN_gaps2.log 2>&1
echo "DONE $(date)" >> logs/hunt_IDN_gaps2.log
