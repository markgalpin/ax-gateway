#!/bin/bash
# echo_agent.sh — The simplest aX agent possible.
#
# This script receives a message, echoes it back with a timestamp.
# That's it. But it proves the point: anything that can read stdin
# or an argument and print to stdout is an aX agent.
#
# Usage:
#   ax listen --agent my_agent --exec ./examples/echo_agent.sh
#
# The mention content arrives as:
#   - Last positional argument: $1
#   - Environment variable: $AX_MENTION_CONTENT

echo "Echo from $(hostname) at $(date -u +%H:%M:%S) UTC: $1"
