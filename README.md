# Sentinel Backend Development Environment

Welcome to the Sentinel project! This repository contains all the microservices for the backend of the Sentinel Misinformation Intelligence Platform.

This project uses a **VS Code Dev Container** to provide a fully configured, one-click development environment. This ensures that every team member has the exact same tools and dependencies, eliminating "it works on my machine" issues, regardless of whether you are on Windows or macOS.

## Prerequisites

Before you begin, you must have the following software installed on your host machine.

<details>
<summary><strong>macOS Setup Instructions</strong></summary>

1.  **Git:** macOS comes with Git pre-installed. You can verify by opening the Terminal and running `git --version`.
2.  **Docker Desktop for Mac:** This is the most important component. It handles all the container and virtualization logic.
    *   [Download Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/) (Choose the correct chip: Apple Silicon or Intel).
    *   After installation, launch the Docker Desktop application. You should see the whale icon in your menu bar.
3.  **Visual Studio Code:** Our primary code editor.
    *   [Download VS Code for macOS](https://code.visualstudio.com/download).
4.  **VS Code "Dev Containers" Extension:** This is what ties everything together.
    *   Launch VS Code, go to the Extensions view (the icon with squares on the left sidebar).
    *   Search for and install `ms-vscode-remote.remote-containers`.

</details>

<details>
<summary><strong>Windows Setup Instructions</strong></summary>

1.  **Git:** For version control.
    *   [Download Git for Windows](https://git-scm.com/download/win).
2.  **WSL2 with Ubuntu:** Our development environment runs on a Linux kernel.
    *   Follow the [Official Microsoft Guide to install WSL](https://learn.microsoft.com/en-us/windows/wsl/install).
    *   From the Microsoft Store, install the **Ubuntu** distribution.
    *   After installation, open a PowerShell/CMD terminal and run `wsl --set-default Ubuntu` to make it your default.
3.  **Docker Desktop for Windows:** For containerization.
    *   [Download Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/).
    *   During setup or in the settings, ensure it is configured to **use the WSL2 backend**.
4.  **Visual Studio Code:** Our primary code editor.
    *   [Download VS Code for Windows](https://code.visualstudio.com/download).
5.  **VS Code "Dev Containers" Extension:** This is what ties everything together.
    *   Launch VS Code, go to the Extensions view.
    *   Search for and install `ms-vscode-remote.remote-containers`.

</details>





## First-Time Setup

The process is nearly identical for both macOS and Windows.

1.  **Clone the Repository:**
    *   **On macOS:** Open your normal Terminal app.
    *   **On Windows:** Open your **Ubuntu terminal** (from the Start Menu).
    *   Navigate to where you want to store your projects (e.g., `cd ~/projects`) and clone the repository:
        ```bash
        git clone <your-repository-url>
        cd sentinel-backend
        ```
    *   **Windows Users:** It is critical that you clone the repository *inside* the WSL filesystem (e.g., in your Ubuntu home directory), not onto your Windows C: drive.

2.  **Launch VS Code:**
    *   From within the `sentinel-backend` directory in your terminal, type the command:
        ```bash
        code .
        ```

3.  **Initial Config:**
    *   Duplicate the .env.template file, rename it to .env, and edit values.
    *   You should have .env.template and .env files at project root now
    *   **Configure PostgreSQL** in your .env file:
        ```bash
        # PostgreSQL Configuration
        POSTGRES_DB=sentinel_db
        POSTGRES_USER=sentinel_user
        POSTGRES_PASSWORD=your_secure_password_here
        POSTGRES_PORT=15432
        DB_SERVICE_PORT=8001
        ```
    *   **Configure PostgreSQL credentials** in your .env file:
        ```bash
        # --- Github Credentials ---
        GITHUB_USER=your_github_username
        GITHUB_EMAIL=your_github_email
        ```
    *   **Configure Redis credentials** in your .env file:
        ```bash
        # --- Redis Configuration ---
        REDIS_HOST=redis
        REDIS_PORT=6379
        ```

4.  **Reopen in Container:**
    * 	Open the container by,
    *   Ctrl + Shift + P
    *   Dev Containers: Rebuild Container & Reopen
    
5.  **Initial Build:**
    *   VS Code will now build the Docker image for the development environment. This will take a significant amount of time (15-30 minutes) as it downloads Docker images, system packages, and all our Python dependencies.
    *   **This is a one-time cost.** Subsequent launches will be much faster.
    *   Once the build is complete, your VS Code window will reload, and you will be inside the fully configured Dev Container. Check the bottom-left corner; it should say **"Dev Container: Sentinel..."**.
    *   **PostgreSQL will start automatically** when the dev container is ready.

## Daily Workflow

1.  **Starting the Environment:**
    *   Open the `sentinel-backend` project folder in VS Code.
    *   Click "Reopen in Container" when prompted. (This will be very fast after the first build).

2.  **Running the Microservice Simulation:**
    *   Open the integrated terminal in VS Code (`Ctrl+` ` ` or `Cmd+` ` ` on Mac). This is a terminal *inside* the container.
    *   Run all the services defined in our simulation using Docker Compose:
        ```bash
        ./scripts/clean.sh && ./scripts/build.sh && ./scripts/deploy.sh
        ```

3.  **Stopping the Services:**
    *   Press `Ctrl+C` in the terminal where `docker-compose` is running.
    *   Double check by running 
        ```bash
        sudo docker-compose down
        ```

## Managing Python Dependencies

All Python packages for the development environment are managed by the `.devcontainer/environment.yml` file. **Do not use `pip install` directly in the terminal for permanent changes.**

To add a new Python package:

1.  Open the `.devcontainer/environment.yml` file.
2.  Add the package name (e.g., `new-package-name`) to the `pip:` section if handled by pip. Otherwise, just make a entry under dependencies.
3.  Save the file.
4.  Open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P` on Mac).
5.  Run the command: **"Dev Containers: Rebuild and Reopen in Container"**.
6.  This will rebuild the environment with your new package installed, ensuring everyone on the team gets it automatically.


## Microservices Architecture

The Sentinel backend consists of several microservices that work together:

### Core Services

*   **API Gateway** (`microservices/api_gateway/`): Main entry point for external requests
*   **Database Service** (`microservices/db/`): PostgreSQL operations and data management
*   **Ingestor** (`microservices/ingestor/`): RSS feed processing and content ingestion
*   **Web Scraper** (`microservices/web_scraper/`): Content extraction from URLs
*   **NLP Service** (`microservices/nlp/`): Natural language processing and analysis

### Infrastructure Services

*   **PostgreSQL**: Primary database with pgvector for semantic search
*   **Redis**: Message queuing and caching

### Service Communication

Services communicate via:
*   **Docker network**: `sentinel-net` for internal communication
*   **REST APIs**: HTTP endpoints for service-to-service calls
*   **Message queues**: Redis streams for asynchronous processing

All services are designed to be stateless and scalable, following microservices best practices.
