#!/bin/bash
set -e

# --- Configuration ---
CONTAINER_NAME="sentinel-redis-container"
STREAMS=(
    "ingestor:to.be.scraped"
    "user-jobs:to.be.scraped"
    "prioritised:to.be.scraped"
)

# --- Color Definitions ---
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Helper Function to Display Stream State ---
# Takes one argument: the name of the stream to inspect.
display_stream_state() {
	local stream_name=$1
	echo -e "${CYAN}=================================================${NC}"
	echo -e "${CYAN}Inspecting Stream: ${YELLOW}${stream_name}${NC}"
	echo -e "${CYAN}=================================================${NC}"

	# 1. Get the total number of messages in the stream.
	echo -e "\n${GREEN}--> Stream Length (XLEN):${NC}"
	sudo docker exec $CONTAINER_NAME redis-cli XLEN "$stream_name"

	# 2. Get high-level information about the consumer group.
	echo -e "\n${GREEN}--> Consumer Group Info (XINFO GROUPS):${NC}"
	# Execute the command and store its output in a variable
	group_info=$(sudo docker exec $CONTAINER_NAME redis-cli --json XINFO GROUPS "$stream_name" || true)

	# Check if the output is not empty and starts with a JSON character ('[' or '{')
	if [[ -n "$group_info" && ("$group_info" == \[* || "$group_info" == {*) ]]; then
		# If it looks like JSON, pipe it to jq
		echo "$group_info" | jq
	else
		# Otherwise, just print the raw output (which might be an error or "(empty array)")
		echo "  (No consumer groups or command failed)"
	fi

	# 3. Show the 5 most recent messages added to the stream.
	echo -e "\n${GREEN}--> 5 Most Recent Messages (XREVRANGE):${NC}"
	sudo docker exec $CONTAINER_NAME redis-cli --json XRANGE "$stream_name" - + COUNT 5 | jq

	# 4. Show a detailed list of up to 5 pending messages.
	echo -e "\n${GREEN}--> Up to 5 Pending Messages (XPENDING):${NC}"

	pending_info=$(sudo docker exec $CONTAINER_NAME redis-cli --json XPENDING "$stream_name" "default" - + 5 || true)

	# Check if the output is not empty and starts with a JSON character ('[' or '{')
	if [[ -n "$pending_info" && ("$pending_info" == \[* || "$pending_info" == {*) ]]; then
		# If it looks like JSON, pipe it to jq
		echo "$pending_info" | jq
	else
		# Otherwise, just print the raw output (which might be an error or "(empty array)")
		echo "  (No pending messages, probably due to no consumer groups or command failed)"
	fi


	echo ""
}

# --- Main Execution ---
for stream in "${STREAMS[@]}"; do
    display_stream_state "$stream"
done
