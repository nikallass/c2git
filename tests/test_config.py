import os
import pytest
from pathlib import Path
from master.util.config import Config
import tempfile
import yaml

@pytest.fixture
def temp_config_file(monkeypatch):
    """Create a temporary config file with test values"""
    # Clear any existing environment variables that might interfere
    for key in os.environ.keys():
        if key.startswith('C2GIT_'):
            monkeypatch.delenv(key)
            
    config_data = {
        "slave_defaults": {
            "linux_local_repo_path": "/tmp/test",
            "windows_local_repo_path": "C:\\Temp\\test",
            "heartbeat_interval": 10,
            "jitter": 5
        },
        "master_defaults": {
            "local_repo_path": "/tmp/test",
            "command_timeout": 60,
            "session_wait_time": 180,
            "job_refresh_rate": 1,
            "job_retry_count": 3,
            "job_retry_delay": 2,
            "crypto_iterations": 100000
        },
        "repo_user": "test_user",
        "repo_name": "test_repo",
        "github_token": "test_token",
        "encryption_key": "test_key",
        "git_user_email": "test@example.com",
        "git_user_name": "Test Bot"
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_file = f.name
    
    yield temp_file
    os.unlink(temp_file)

def test_generate_agent_with_dotenv(temp_config_file):
    """Test generating agent with .env file in config directory"""
    config_dir = os.path.dirname(temp_config_file)
    env_content = """
C2GIT_REPO_USER=dotenv_user
C2GIT_REPO_NAME=dotenv_repo
C2GIT_GITHUB_TOKEN=dotenv_token
C2GIT_ENCRYPTION_KEY=dotenv_key
C2GIT_GIT_USER_EMAIL=dotenv@example.com
C2GIT_GIT_USER_NAME=Dotenv Bot
"""
    env_file = os.path.join(config_dir, '.env')
    with open(env_file, 'w') as f:
        f.write(env_content)
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            output_path = f.name
            
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent))
        from c2git import generate_agent
        generate_agent(temp_config_file, 'py', output_path)
        
        with open(output_path, 'r') as f:
            content = f.read()
            
        # Verify .env values were used
        assert 'dotenv_user' in content
        assert 'dotenv_repo' in content
        assert 'dotenv_token' in content
        assert 'dotenv_key' in content
        assert 'dotenv@example.com' in content
        assert 'Dotenv Bot' in content
    finally:
        os.unlink(env_file)
        os.unlink(output_path)

def test_generate_agent_env_priority(temp_config_file, monkeypatch):
    """Test that environment variables take priority when generating agent"""
    # Set environment variables
    env_vars = {
        'C2GIT_REPO_USER': 'env_user',
        'C2GIT_REPO_NAME': 'env_repo',
        'C2GIT_GITHUB_TOKEN': 'env_token',
        'C2GIT_ENCRYPTION_KEY': 'env_key',
        'C2GIT_GIT_USER_EMAIL': 'env@example.com',
        'C2GIT_GIT_USER_NAME': 'Env Bot'
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        output_path = f.name
    
    try:
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent))
        from c2git import generate_agent
        generate_agent(temp_config_file, 'py', output_path)
        
        with open(output_path, 'r') as f:
            content = f.read()
            
        # Verify environment values were used
        assert 'env_user' in content
        assert 'env_repo' in content
        assert 'env_token' in content
        assert 'env_key' in content
        assert 'env@example.com' in content
        assert 'Env Bot' in content
    finally:
        os.unlink(output_path)

@pytest.fixture
def temp_env_file():
    """Create a temporary .env file with test values"""
    env_content = """
C2GIT_REPO_USER=env_user
C2GIT_REPO_NAME=env_repo
C2GIT_GITHUB_TOKEN=env_token
C2GIT_ENCRYPTION_KEY=env_key
C2GIT_GIT_USER_EMAIL=env@example.com
C2GIT_GIT_USER_NAME=Env Bot
C2GIT_COMMAND_TIMEOUT=120
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(env_content)
        temp_file = f.name
    
    yield temp_file
    os.unlink(temp_file)

def test_config_from_yaml(temp_config_file):
    """Test loading configuration from YAML file"""
    config = Config.from_yaml(temp_config_file)
    
    assert config.repo_user == "test_user"
    assert config.repo_name == "test_repo"
    assert config.github_token == "test_token"
    assert config.encryption_key == "test_key"
    assert config.command_timeout == 60
    assert config.git_user_email == "test@example.com"
    assert config.git_user_name == "Test Bot"
    assert config.slave_defaults["heartbeat_interval"] == 10

def test_config_from_env(temp_config_file, monkeypatch):
    """Test loading configuration from environment variables"""
    # Clear any existing env vars first
    for key in list(os.environ.keys()):
        if key.startswith('C2GIT_'):
            monkeypatch.delenv(key)
            
    # Set test environment variables
    os.environ["C2GIT_REPO_USER"] = "env_user"
    os.environ["C2GIT_REPO_NAME"] = "env_repo"
    os.environ["C2GIT_GITHUB_TOKEN"] = "env_token"
    os.environ["C2GIT_COMMAND_TIMEOUT"] = "120"
    
    config = Config.from_yaml(temp_config_file)
    
    assert config.repo_user == "env_user"
    assert config.repo_name == "env_repo"
    assert config.github_token == "env_token"
    assert config.command_timeout == 120
    

def test_config_from_env_file(temp_config_file, temp_env_file, monkeypatch):
    """Test loading configuration from .env file"""
    config = Config.from_yaml(temp_config_file, env_file=temp_env_file)
    
    assert config.repo_user == "env_user"
    assert config.repo_name == "env_repo"
    assert config.github_token == "env_token"
    assert config.encryption_key == "env_key"
    assert config.command_timeout == 120
    assert config.git_user_email == "env@example.com"
    assert config.git_user_name == "Env Bot"

def test_config_validation():
    """Test configuration validation"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            "slave_defaults": {
                "linux_local_repo_path": "/tmp/test",
                "windows_local_repo_path": "C:\\Temp\\test",
                "heartbeat_interval": 10,
                "jitter": 5
            },
            "repo_user": "test_user",
            "repo_name": "test_repo",
            "master_defaults": {
                "command_timeout": 60
            }
            # Missing other required fields
        }, f)
        temp_file = f.name

    with pytest.raises(ValueError) as exc_info:
        Config.from_yaml(temp_file)
    assert "Missing required fields" in str(exc_info.value)
    
    os.unlink(temp_file)

def test_invalid_yaml():
    """Test handling of invalid YAML file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("invalid: yaml: content:")
        temp_file = f.name

    with pytest.raises(ValueError) as exc_info:
        Config.from_yaml(temp_file)
    assert "Invalid YAML format" in str(exc_info.value)
    
    os.unlink(temp_file)
