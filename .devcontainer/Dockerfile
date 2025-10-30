# Start from Microsoft's recommended base image for Ubuntu.
FROM mcr.microsoft.com/devcontainers/base:ubuntu

# --- Set Default Arguments for Git Config ---
ARG GITHUB_USER
ARG GITHUB_EMAIL

# Propagate args as environment variables
ENV GITHUB_USER=${GITHUB_USER}
ENV GITHUB_EMAIL=${GITHUB_EMAIL}

# --- Install System-Level Prerequisite Packages ---
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    redis-tools \
    postgresql-client \
    jq \
    expect

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
ARG TARGETPLATFORM
ENV PATH=$CONDA_DIR/bin:$PATH

RUN case "$TARGETPLATFORM" in \
      linux/amd64) MINICONDA=Miniconda3-latest-Linux-x86_64.sh ;; \
      linux/arm64) MINICONDA=Miniconda3-latest-Linux-aarch64.sh ;; \
      *) echo "Unsupported TARGETPLATFORM: $TARGETPLATFORM" && exit 1 ;; \
    esac \
    && curl -sSL "https://repo.anaconda.com/miniconda/${MINICONDA}" -o /tmp/miniconda.sh \
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
COPY core-environment.yml /tmp/core-environment.yml
RUN conda env create -f /tmp/core-environment.yml && rm /tmp/core-environment.yml

COPY environment.yml /tmp/environment.yml
RUN conda env update --name sentinel-env --file /tmp/environment.yml --prune && rm /tmp/environment.yml


# Set up shell to automatically activate our new environment
RUN echo "source $CONDA_DIR/bin/activate sentinel-env" >> /etc/bash.bashrc
ENV BASH_ENV=/etc/bash.bashrc

# --- Docker group setup for vscode user ---
RUN groupadd --gid 999 docker && \
    usermod -aG docker vscode && \
    chown -R vscode:vscode $CONDA_DIR

# --- Auto-configure Git if env vars available ---
RUN if [ -n "$GITHUB_USER" ] && [ -n "$GITHUB_EMAIL" ]; then \
        git config --global user.name "$GITHUB_USER" && \
        git config --global user.email "$GITHUB_EMAIL" && \
        echo "Configured git with $GITHUB_USER <$GITHUB_EMAIL>"; \
    else \
        echo "GITHUB_USER or GITHUB_EMAIL not provided; skipping git config."; \
    fi

USER vscode
