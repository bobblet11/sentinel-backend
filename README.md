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
    *   Add your git credentials to the .env

4.  **Reopen in Container:**
    * 	Open the container by,
    *   Ctrl + Shift + P
    *   Dev Containers: Rebuild Container & Reopen
    
5.  **Initial Build:**
    *   VS Code will now build the Docker image for the development environment. This will take a significant amount of time (15-30 minutes) as it downloads Docker images, system packages, and all our Python dependencies.
    *   **This is a one-time cost.** Subsequent launches will be much faster.
    *   Once the build is complete, your VS Code window will reload, and you will be inside the fully configured Dev Container. Check the bottom-left corner; it should say **"Dev Container: Sentinel..."**.





## Daily Workflow

1.  **Starting the Environment:**
    *   Open the `sentinel-backend` project folder in VS Code.
    *   Click "Reopen in Container" when prompted. (This will be very fast after the first build).

2.  **Running the Microservice Simulation:**
    *   Open the integrated terminal in VS Code (`Ctrl+` ` ` or `Cmd+` ` ` on Mac). This is a terminal *inside* the container.
    *   Run all the services defined in our simulation using Docker Compose:
        ```bash
        docker-compose up --build
        ```
    *   You will see the logs from all the microservices streaming in this terminal.

3.  **Stopping the Services:**
    *   Press `Ctrl+C` in the terminal where `docker-compose` is running.
    *   To fully remove the containers and networks, run:
        ```bash
        docker-compose down
        ```






## Managing Python Dependencies

All Python packages for the project are managed by the `.devcontainer/environment.yml` file. **Do not use `pip install` directly in the terminal for permanent changes.**

To add a new Python package:

1.  Open the `.devcontainer/environment.yml` file.
2.  Add the package name (e.g., `new-package-name`) to the `pip:` section.
3.  Save the file.
4.  Open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P` on Mac).
5.  Run the command: **"Dev Containers: Rebuild and Reopen in Container"**.
6.  This will rebuild the environment with your new package installed, ensuring everyone on the team gets it automatically.