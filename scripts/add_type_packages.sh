#!/bin/bash
set -e

ENV_FILE="./.devcontainer/environment.yml"

# --- Safety check ---
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: Environment file '$ENV_FILE' not found."
    exit 1
fi

echo "==> Running mypy to find missing type stubs..."

# Run mypy and capture its stderr, where hints are printed.
# We add '|| true' so the script doesn't exit if mypy finds errors.
MISSING_STUBS=$(mypy . --ignore-missing-imports 2>&1 || true)

# Isolate the lines that recommend installing types packages,
# extract just the package name, and get a unique sorted list.
PACKAGES_TO_INSTALL=$(echo "$MISSING_STUBS" | \
    grep 'Hint: ".*pip install' | \
    sed -n 's/.*pip install \(types-[^"]*\).*/\1/p' | \
    sort -u)

# --- Check if there's anything to do ---
if [ -z "$PACKAGES_TO_INSTALL" ]; then
    echo "==> No new missing type stubs found. Your environment file is up to date."
    exit 0
fi

echo "==> Found the following missing stub packages:"
echo "$PACKAGES_TO_INSTALL"
echo ""

# --- Update the environment.yml file ---
echo "==> Updating '$ENV_FILE'..."

# This is a bit of bash magic. We loop through each package.
# For each one, we check if it's already in the file. If not, we append it.
while IFS= read -r package; do
    # Check if the package is already listed under the pip section
    if grep -q "^\s*-\s*$package" "$ENV_FILE"; then
        echo "-> '$package' is already in $ENV_FILE. Skipping."
    else
        echo "-> Adding '$package' to $ENV_FILE."
        # Append the package under the pip section.
        # This uses sed to find the 'pip:' line and add the package after it.
        sed -i "/^\s*-\s*pip:/a \ \ \ \ - $package" "$ENV_FILE"
    fi
done <<< "$PACKAGES_TO_INSTALL"

echo ""
echo "==> Update complete. Please rebuild your Conda environment."
echo "    conda env update --file $ENV_FILE --prune"

echo "==> Installing new packages..."
sudo conda env update --file ./.devcontainer/environment.yml --prune
