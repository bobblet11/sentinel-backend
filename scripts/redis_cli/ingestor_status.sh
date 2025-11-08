#!/bin/bash
set -e

# --- Configuration ---
# All your Redis keys and names are in one place for easy changes.
CONTAINER_NAME="sentinel-redis-container"
SEEN_SET_KEY="ingestor:seen.articles"
STREAM_KEY="ingestor:to.be.scraped"
GROUP_NAME="default"

# --- Color Definitions ---
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Main Status Function ---
# This function provides a full health check of the ingestion pipeline.
display_ingestion_status() {
    echo -e "${CYAN}==============================================${NC}"
    echo -e "${CYAN}    Ingestion Service Health Check${NC}"
    echo -e "${CYAN}==============================================${NC}"

    # --- Part 1: Check the 'Seen' Set ---
    # This tells us about the historical work done.
    echo -e "\n${GREEN}--- 'Seen Articles' Set Status (${YELLOW}${SEEN_SET_KEY}${GREEN}) ---${NC}"

    echo -e "\n${YELLOW}--> Total Articles Processed (SCARD):${NC}"
    sudo docker exec $CONTAINER_NAME redis-cli SCARD "$SEEN_SET_KEY"

    echo -e "\n${YELLOW}--> Sample of 5 Seen Articles (SRANDMEMBER):${NC}"
    sudo docker exec $CONTAINER_NAME redis-cli SRANDMEMBER "$SEEN_SET_KEY" 5

    # --- Part 2: Live Pipeline Status ---
    echo -e "\n${GREEN}--- 'To Be Scraped' Stream (${YELLOW}${STREAM_KEY}${GREEN}) ---${NC}"

    echo -e "\n${YELLOW}--> Consumer Group Health Summary (XINFO GROUPS):${NC}"
    echo -e "${NC}This is the most important health metric.
  - ${CYAN}lag${NC}: Unread items, waiting to be delivered.
  - ${RED}pending${NC}: Items delivered but not acknowledged (stuck).${NC}"
    sudo docker exec $CONTAINER_NAME redis-cli --json XINFO GROUPS "$STREAM_KEY" | jq

    echo -e "\n${YELLOW}--> Total Items in Stream's History (XLEN):${NC}"
    echo -e "${NC}(This shows the current size of the data window, not the backlog)${NC}"
    sudo docker exec $CONTAINER_NAME redis-cli XLEN "$STREAM_KEY"

    echo -e "\n${YELLOW}--> 5 Newest Items (Confirms producer is working - XREVRANGE):${NC}"
    sudo docker exec $CONTAINER_NAME redis-cli --json XREVRANGE "$STREAM_KEY" + - COUNT 5 | jq

    echo -e "\n${RED}--> Details of up to 5 Pending/Stuck Items (XPENDING):${NC}"
    sudo docker exec $CONTAINER_NAME redis-cli --json XPENDING "$STREAM_KEY" "$GROUP_NAME" - + 5 | jq

    echo -e "\n${CYAN}==============================================${NC}\n"
}

# --- Main Execution ---
display_ingestion_status
