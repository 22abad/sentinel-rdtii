#!/usr/bin/env bash
set -uo pipefail
# Pipeline watcher — keeps 2 batch_run processes running at all times
# Usage:  bash pipeline_watcher.sh [PID1 PID2 ...]
# Queue order: Indonesia, Lao PDR, Mongolia, Russian Federation, Thailand

WORKDIR="/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private"
cd "$WORKDIR"

# Global queue (do NOT prepopulate CHN/IND — they're already running)
declare -a QUEUE=( "Indonesia" "Lao PDR" "Mongolia" "Russian Federation" "Thailand" )
declare -a PIDS=()

# Register running PIDs passed as arguments
register() {
  while [ $# -gt 0 ]; do
    local pid=$1; shift
    if kill -0 "$pid" 2>/dev/null; then
      PIDS+=("$pid")
    fi
  done
}

# Launch next economy from queue
launch_next() {
  if [ ${#QUEUE[@]} -eq 0 ]; then
    return 1
  fi
  local econ="${QUEUE[0]}"
  QUEUE=("${QUEUE[@]:1}")
  local key=$(echo "$econ" | sed 's/ .*//')
  echo "[$(date '+%H:%M:%S')] Launching: $econ"
  nohup python batch_run.py \
    --economies "$econ" \
    --pillar all \
    --from-corpus \
    --provider ollama \
    --output-dir outputs \
    > "/tmp/${key}_out.txt" 2>"/tmp/${key}_err.txt" &
  local pid=$!
  PIDS+=("$pid")
  echo "[$(date '+%H:%M:%S')]   PID $pid started"
  return 0
}

# Register existing PIDs passed as arguments
register "$@"

# Main loop — keep 2 running
echo "[$(date '+%H:%M:%S')] Pipeline watcher started"
echo "[$(date '+%H:%M:%S')] Running PIDs: ${PIDS[*]:-none}"
echo "[$(date '+%H:%M:%S')] Queue: ${QUEUE[*]}"
echo ""

while true; do
  # Prune dead PIDs
  ALIVE=()
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      ALIVE+=("$pid")
    fi
  done
  PIDS=("${ALIVE[@]}")

  local_count=${#PIDS[@]}
  echo "[$(date '+%H:%M:%S')] Running: $local_count, Remaining in queue: ${#QUEUE[@]}"

  if [ "$local_count" -lt 2 ] && [ ${#QUEUE[@]} -gt 0 ]; then
    # Launch until we have 2 running or queue is empty
    while [ "$local_count" -lt 2 ] && [ ${#QUEUE[@]} -gt 0 ]; do
      if launch_next; then
        local_count=$((local_count + 1))
      fi
    done
  fi

  # If nothing running and queue empty → done
  if [ "$local_count" -eq 0 ] && [ ${#QUEUE[@]} -eq 0 ]; then
    echo "[$(date '+%H:%M:%S')] All economies done!"
    break
  fi

  sleep 30
done

echo "[$(date '+%H:%M:%S')] Pipeline complete"
