import base64
from typing import Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os

class Crypto:
    def __init__(self, key: str):
        """Initialize crypto with key"""
        self.key = key.encode()

    def _derive_key_iv(self, salt: bytes) -> bytes:
        """PBKDF2 key derivation with 100000 iterations"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=48,  # 32 for key, 16 for IV
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(self.key)

    def encrypt(self, text: str) -> str:
        """Encrypt text using AES-256-CBC with PBKDF2"""
        if not text:
            return ""
        
        try:
            # Generate random salt (8 bytes for OpenSSL compatibility)
            salt = os.urandom(8)
            
            # PBKDF2 key derivation
            key_iv = self._derive_key_iv(salt)
            key = key_iv[:32]  # First 32 bytes for key
            iv = key_iv[32:48]  # Next 16 bytes for IV
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # Pad and encode the plaintext
            padded_data = self._pad(text.encode('utf-8'))
            
            # Encrypt the data
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            
            # OpenSSL format: Salted__<8 bytes salt><encrypted data>
            formatted = b'Salted__' + salt + ciphertext
            return base64.b64encode(formatted).decode('utf-8')
            
        except Exception as e:
            print(f"Encryption error: {e}")
            return ""

    def decrypt(self, encrypted_text: str) -> Optional[str]:
        """Decrypt OpenSSL compatible AES-256-CBC text with PBKDF2"""
        if not encrypted_text:
            return None
            
        try:
            # Decode base64
            try:
                encrypted_data = base64.b64decode(encrypted_text.strip())
            except Exception as e:
                raise ValueError(f"Invalid base64 encoding: {str(e)}")
            
            # Check for OpenSSL format
            if not encrypted_data.startswith(b'Salted__'):
                raise ValueError("Not in OpenSSL format (missing 'Salted__' prefix)")
                
            if len(encrypted_data) < 16:
                raise ValueError(f"Data too short - missing salt. Length: {len(encrypted_data)}")
                
            # Extract salt and ciphertext
            salt = encrypted_data[8:16]  # 8 bytes after "Salted__"
            ciphertext = encrypted_data[16:]
            
            if len(ciphertext) == 0:
                raise ValueError("Empty ciphertext")
                
            if len(ciphertext) % 16 != 0:
                raise ValueError(f"Invalid ciphertext length: {len(ciphertext)} (not multiple of 16)")
            
            # PBKDF2 key derivation
            try:
                key_iv = self._derive_key_iv(salt)
                key = key_iv[:32]  # First 32 bytes for key
                iv = key_iv[32:48]  # Next 16 bytes for IV
            except Exception as e:
                raise ValueError(f"Key derivation failed: {str(e)}")
            
            # Create cipher
            try:
                cipher = Cipher(
                    algorithms.AES(key),
                    modes.CBC(iv),
                    backend=default_backend()
                )
                decryptor = cipher.decryptor()
            except Exception as e:
                raise ValueError(f"Cipher creation failed: {str(e)}")
            
            # Decrypt and unpad
            try:
                decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()
            except Exception as e:
                raise ValueError(f"Decryption failed: {str(e)}")
                
            try:
                unpadded_data = self._unpad(decrypted_data)
            except ValueError as e:
                raise ValueError(f"Unpadding failed: {str(e)}")
                
            try:
                return unpadded_data.decode('utf-8')
            except UnicodeDecodeError as e:
                raise ValueError(f"UTF-8 decoding failed: {str(e)}")
            
        except ValueError as e:
            raise e
        except Exception as e:
            raise ValueError(f"Unexpected error in decrypt: {str(e)}")

    def _pad(self, data: bytes) -> bytes:
        """PKCS7 padding"""
        block_size = 16
        padding_length = block_size - (len(data) % block_size)
        padding = bytes([padding_length] * padding_length)
        return data + padding

    def _unpad(self, padded_data: bytes) -> bytes:
        """Remove PKCS7 padding"""
        if not padded_data:
            raise ValueError("Empty data")
            
        # Get the last byte as an integer
        padding_length = padded_data[-1]
        
        # Validate padding length
        if padding_length == 0 or padding_length > 16:
            # Try to recover by checking other common padding lengths
            for i in range(1, 17):
                if len(padded_data) >= i and all(x == i for x in padded_data[-i:]):
                    return padded_data[:-i]
            raise ValueError(f"Could not find valid padding")
            
        # Verify we have enough data
        if len(padded_data) < padding_length:
            raise ValueError("Data shorter than padding length")
            
        # Verify padding bytes
        padding = padded_data[-padding_length:]
        if all(x == padding_length for x in padding):
            return padded_data[:-padding_length]
            
        # Try to recover by checking actual padding bytes
        for i in range(1, 17):
            if len(padded_data) >= i and all(x == i for x in padded_data[-i:]):
                return padded_data[:-i]
                
        raise ValueError("Invalid padding")
