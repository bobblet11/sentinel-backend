#!/bin/bash
set -e


while true; do
    echo "This will clear all images and all volumes!"
    read -p "Do you wish to delete everything? [y/n]" yn
    case $yn in
        [Yy]* ) break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
done


# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)

echo "==> Project root identified as: $PROJECT_ROOT"

cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

echo "==> Spinning down containers"
sudo -E docker-compose down || true

echo "==> Pruning old Docker build cache..."
sudo -E docker system prune --all --force 

echo "==> Forcefully removing old service images to prevent tag conflicts..."
sudo -E docker-compose rm --stop --force
sudo -E docker-compose down --rmi local -v --remove-orphans || true

echo "==> Clean complete."
