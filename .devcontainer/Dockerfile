# Start from Microsoft's recommended base image for Ubuntu.
# This image already includes a non-root user 'vscode' and other common tools.
FROM mcr.microsoft.com/devcontainers/base:ubuntu



# --- Install System-Level Prerequisite Packages ---
# We still need to do this to get the Docker CLI, etc.
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    redis-tools \
    postgresql-client

# --- Add Docker's Official GPG Key and Set Up The Repository ---
RUN mkdir -p /etc/apt/keyrings
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
RUN echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# --- Install Docker Engine CLI and Docker Compose ---
RUN apt-get update \
    && apt-get -y install docker-ce-cli
RUN curl -SL "https://github.com/docker/compose/releases/download/v2.17.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose \
    && chmod +x /usr/local/bin/docker-compose


# --- Install Miniconda and Create Environment ---
ARG CONDA_DIR=/opt/conda
ENV PATH=$CONDA_DIR/bin:$PATH

RUN curl -sSL "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh" -o /tmp/miniconda.sh \
    && /bin/bash /tmp/miniconda.sh -b -p $CONDA_DIR \
    && rm /tmp/miniconda.sh \
    && conda clean -afy

# Pre-configure Conda and Accept Terms of Service
RUN conda config --set auto_activate_base false \
    && conda config --set show_channel_urls true \
    && conda config --append channels conda-forge \
    && conda config --set channel_priority strict \
    && conda tos accept

# Create the Conda Environment
COPY environment.yml /tmp/environment.yml
RUN conda env create -f /tmp/environment.yml && rm /tmp/environment.yml

# Set up shell to automatically activate our new environment
RUN echo "source $CONDA_DIR/bin/activate sentinel-env" >> /etc/bash.bashrc
ENV BASH_ENV=/etc/bash.bashrc

# We use a fixed GID (Group ID) which is common for the docker group
RUN groupadd --gid 999 docker

# Add the vscode user to the docker group so they can run docker commands without sudo
RUN usermod -aG docker vscode

# Give the vscode user ownership of the conda directory so they can install packages
RUN chown -R vscode:vscode $CONDA_DIR