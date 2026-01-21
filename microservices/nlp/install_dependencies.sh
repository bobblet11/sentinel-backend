#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "--- 1. Upgrading pip ---"
python3 -m pip install --upgrade pip

echo "--- 2. Installing PyTorch with CUDA 12.1 support ---"
# We must install this BEFORE the requirements file to prevent pip from 
# grabbing the CPU version of torch from the default index.
pip3 install torch==2.4.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo "--- 3. Installing Project Requirements ---"
pip3 install -r requirements.txt

echo "--- 4. Downloading Spacy Language Model ---"
# Required for the Preprocessor component
python3 -m spacy download en_core_web_sm

echo "--- Installation Complete! ---"
echo "To verify GPU support, run: python3 -c 'import torch; print(torch.cuda.is_available())'"