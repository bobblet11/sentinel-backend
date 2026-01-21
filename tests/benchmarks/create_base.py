import os
import json
from pathlib import Path
from typing import Dict, Any
import docker
import subprocess

class ConfigManager:
    def __init__(self, env_name: str = "dev"):
        self.env_name = env_name
        self.config = self.load_config()
        self.docker_client = docker.from_env()
    
    def load_config(self) -> Dict[str, Any]:
        """Load config from environment-specific files."""
        env_dir = Path("/app/")
        env_dir.mkdir(exist_ok=True)
        
        config_dir = Path("/app/tests/test_configs")
        config_dir.mkdir(exist_ok=True)
        
        # Load base config
        base_config = self.read_json(config_dir / "base.json")
        
        # Override with environment-specific
        env_config = self.read_json(config_dir / f"{self.env_name}.json")
        config = {**base_config, **env_config}
        
        # Override with .env file
        for key, value in self.read_env(env_dir / ".env"):
            config[key] = value
            
        return config
    
    def read_json(self, path: Path) -> Dict:
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return {}
    
    def read_env(self, path: Path) -> Dict:
        env = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()
        return env
    
    def get(self, key: str, default=None):
        return self.config.get(key, default)
