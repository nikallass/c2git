from dataclasses import dataclass
from typing import Optional, Dict, Any
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv

@dataclass
class Config:
    """Configuration class for c2git"""
    local_repo_path: str
    repo_user: str
    repo_name: str
    github_token: str
    encryption_key: str
    command_timeout: int
    git_user_email: str
    git_user_name: str
    session_wait_time: int
    job_refresh_rate: int
    job_retry_count: int
    job_retry_delay: int
    crypto_iterations: int
    slave_defaults: dict

    @property
    def repo_url(self) -> str:
        """Construct repository URL from user and name with authentication token"""
        return f"https://{self.github_token}@github.com/{self.repo_user}/{self.repo_name}.git"

    @classmethod
    def from_yaml(cls, path: str, env_file: Optional[str] = None) -> 'Config':
        """Load configuration in order of priority:
        1. Environment variables
        2. .env file
        3. config.yaml
        4. defaults
        """
        # 1. Load defaults from YAML first
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, 'r') as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML format: {e}")

        if not isinstance(data, dict):
            raise ValueError("Configuration file must contain a YAML dictionary")

        # Get defaults
        defaults = data.get('master_defaults', {})
        if not isinstance(defaults, dict):
            raise ValueError("master_defaults must be a dictionary")

        # 2. Apply YAML config over defaults
        config_data = cls._merge_config_with_defaults(data, defaults)

        # 3. Load .env file if specified or look in config directory
        if env_file is None:
            env_file = os.path.join(os.path.dirname(path), '.env')
        if os.path.exists(env_file):
            load_dotenv(env_file, override=True)

        # 4. Apply environment variables (highest priority)
        config_data = cls._apply_environment_variables(config_data)

        # Process and validate
        config_data = cls._process_special_fields(config_data)
        
        # Check required fields before instantiation
        required_fields = ['local_repo_path', 'github_token', 'encryption_key', 
                          'git_user_email', 'git_user_name', 'session_wait_time',
                          'job_refresh_rate', 'job_retry_count', 'job_retry_delay',
                          'crypto_iterations']
        missing_fields = [field for field in required_fields if field not in config_data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
            
        try:
            return cls(**config_data)
        except TypeError as e:
            raise ValueError(f"Configuration error: {e}")

    @staticmethod
    def _merge_config_with_defaults(data: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
        """Merge configuration data with defaults"""
        merged = {
            **defaults,
            **{k: v for k, v in data.items() if k not in ['master_defaults']},
            'slave_defaults': data.get('slave_defaults', {})  # Explicitly preserve slave_defaults
        }
        return merged

    @staticmethod
    def _apply_environment_variables(config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variables to configuration in order of priority"""
        env_mappings = {
            'encryption_key': 'C2GIT_ENCRYPTION_KEY',
            'github_token': 'C2GIT_GITHUB_TOKEN',
            'repo_user': 'C2GIT_REPO_USER',
            'repo_name': 'C2GIT_REPO_NAME',
            'git_user_email': 'C2GIT_GIT_USER_EMAIL',
            'git_user_name': 'C2GIT_GIT_USER_NAME',
            'command_timeout': 'C2GIT_COMMAND_TIMEOUT',
            'session_wait_time': 'C2GIT_SESSION_WAIT_TIME',
            'job_refresh_rate': 'C2GIT_JOB_REFRESH_RATE'
        }

        for config_key, env_key in env_mappings.items():
            # Priority 1: Environment variables
            value = os.getenv(env_key)
            
            if value is not None:
                if config_key in ['command_timeout', 'session_wait_time', 'job_refresh_rate']:
                    try:
                        config_data[config_key] = int(value)
                    except ValueError:
                        raise ValueError(f"Environment variable {env_key} must be an integer")
                else:
                    config_data[config_key] = value

        return config_data

    @staticmethod
    def _process_special_fields(config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process special configuration fields"""
        # Save slave_defaults before removing
        slave_defaults = config_data.get('slave_defaults', {})
        
        # Remove extra fields not in Config class
        config_data.pop('slave_defaults', None)
        config_data.pop('master_defaults', None)

        # Add slave_defaults back
        config_data['slave_defaults'] = slave_defaults

        # Handle repo user and name first
        repo_user = os.getenv('C2GIT_REPO_USER', config_data.get('repo_user'))
        repo_name = os.getenv('C2GIT_REPO_NAME', config_data.get('repo_name'))
        
        if not repo_user or not repo_name:
            raise ValueError("Both repo_user and repo_name must be provided")
            
        config_data['repo_user'] = repo_user
        config_data['repo_name'] = repo_name

        # Then check other required fields
        required_fields = ['github_token', 'encryption_key', 'git_user_email', 'git_user_name']
        missing_fields = [field for field in required_fields if not config_data.get(field)]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        # Ensure repo_path is absolute and exists
        if 'local_repo_path' in config_data:
            local_repo_path = Path(os.path.expanduser(config_data['local_repo_path'])).absolute()
            local_repo_path.mkdir(parents=True, exist_ok=True)
            config_data['local_repo_path'] = str(local_repo_path)

        return config_data

    def validate(self) -> None:
        """Validate configuration values"""
        if not self.github_token:
            raise ValueError("GitHub token is required")
        if not self.encryption_key:
            raise ValueError("Encryption key is required")
        if self.command_timeout <= 0:
            raise ValueError("Command timeout must be positive")
        if self.session_wait_time <= 0:
            raise ValueError("Session wait time must be positive")
        if self.job_refresh_rate <= 0:
            raise ValueError("Job refresh rate must be positive")
            
        # Validate slave_defaults
        required_slave_defaults = ['linux_local_repo_path', 'windows_local_repo_path', 'heartbeat_interval', 'jitter']
        missing_fields = [field for field in required_slave_defaults if field not in self.slave_defaults]
        if missing_fields:
            raise ValueError(f"Missing required fields in slave_defaults: {', '.join(missing_fields)}")
