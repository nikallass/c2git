import base64
import os
import subprocess
import tempfile
from typing import Tuple
import pytest
from master.core.crypto import Crypto

def openssl_encrypt(text: str, password: str) -> str:
    """Encrypt using OpenSSL CLI with PBKDF2"""
    cmd = [
        'openssl', 'enc', '-aes-256-cbc',
        '-pbkdf2', '-iter', '100000',
        '-salt', '-base64', '-A',
        '-pass', f'pass:{password}'
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(text.encode())
    if proc.returncode != 0:
        raise RuntimeError(f"OpenSSL encryption failed: {stderr.decode()}")
    return stdout.decode().strip()

def openssl_decrypt(encrypted: str, password: str) -> str:
    """Decrypt using OpenSSL CLI with PBKDF2"""
    cmd = [
        'openssl', 'enc', '-aes-256-cbc',
        '-pbkdf2', '-iter', '100000',
        '-salt', '-base64', '-d', '-A',
        '-pass', f'pass:{password}'
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(encrypted.encode() + b'\n')
    if proc.returncode != 0:
        raise RuntimeError(f"OpenSSL decryption failed: {stderr.decode()}")
    return stdout.decode()

@pytest.fixture
def crypto():
    return Crypto("testkey123")

def test_python_encrypt_openssl_decrypt(crypto):
    """Test that OpenSSL can decrypt Python's encryption"""
    original = "Hello, World!"
    encrypted = crypto.encrypt(original)
    decrypted = openssl_decrypt(encrypted, "testkey123")
    assert decrypted == original

def test_openssl_encrypt_python_decrypt(crypto):
    """Test that Python can decrypt OpenSSL's encryption"""
    original = "Hello, World!"
    encrypted = openssl_encrypt(original, "testkey123")
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == original

def test_empty_string(crypto):
    """Test handling of empty string"""
    assert crypto.encrypt("") == ""
    assert crypto.decrypt("") is None

def test_special_characters(crypto):
    """Test encryption/decryption of special characters"""
    original = "Hello\n\t!@#$%^&*()_+-=[]{}|;:,.<>?"
    encrypted = crypto.encrypt(original)
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == original

def test_long_text(crypto):
    """Test encryption/decryption of long text"""
    original = "x" * 1000
    encrypted = crypto.encrypt(original)
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == original

def test_unicode(crypto):
    """Test encryption/decryption of Unicode characters"""
    original = "Hello, 世界! 👋"
    encrypted = crypto.encrypt(original)
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == original

def test_shell_script_compatibility(crypto):
    """Test compatibility with shell script encryption"""
    # Create temporary test script
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write('''#!/bin/bash
KEY="testkey123"
encrypt() {
    local input="$1"
    if [ -z "$input" ]; then
        echo ""
        return 0
    fi
    echo -n "$input" | openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -base64 -A -pass pass:"$KEY" 2>/dev/null
}
decrypt() {
    local input="$1"
    if [ -z "$input" ]; then
        return 1
    fi
    echo -n "$input" | openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -base64 -d -A -pass pass:"$KEY" 2>/dev/null
    return $?
}
case "$1" in
    "encrypt") encrypt "$2" ;;
    "decrypt") decrypt "$2" ;;
esac
''')
        test_script = f.name
    
    os.chmod(test_script, 0o755)
    
    try:
        # Test Python encrypt -> Shell decrypt
        original = "Hello, World!"
        encrypted = crypto.encrypt(original)
        proc = subprocess.run([test_script, "decrypt", encrypted], 
                            capture_output=True, text=True)
        assert proc.returncode == 0
        assert proc.stdout.strip() == original
        
        # Test Shell encrypt -> Python decrypt
        proc = subprocess.run([test_script, "encrypt", original], 
                            capture_output=True, text=True)
        assert proc.returncode == 0
        shell_encrypted = proc.stdout.strip()
        assert crypto.decrypt(shell_encrypted) == original
        
        # Test empty string handling
        assert subprocess.run([test_script, "encrypt", ""], 
                            capture_output=True, text=True).stdout.strip() == ""
        assert subprocess.run([test_script, "decrypt", ""], 
                            capture_output=True, text=True).returncode == 1
    finally:
        os.unlink(test_script)
