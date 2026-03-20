"""KMS field encryption for workspace secrets."""

import base64

import boto3


class FieldEncryptor:
    """Encrypts and decrypts individual fields using AWS KMS.

    Intended for storing workspace secrets (tokens, credentials) in DynamoDB.
    Each value is encrypted via KMS and stored as a base64-encoded string.
    """

    def __init__(self, kms_key_id: str) -> None:
        """Initialise the encryptor with a KMS key ARN or alias.

        Args:
            kms_key_id: The KMS key ARN, key ID, or alias used for encrypt/decrypt.
        """
        self._kms_key_id = kms_key_id
        self._client = boto3.client("kms")

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string and return a base64-encoded ciphertext.

        Args:
            plaintext: The string to encrypt. Must be non-empty.

        Returns:
            A base64-encoded string containing the KMS ciphertext blob.

        Raises:
            ValueError: If ``plaintext`` is empty.
            botocore.exceptions.ClientError: On KMS API errors.
        """
        if not plaintext:
            raise ValueError("plaintext must not be empty")

        response = self._client.encrypt(
            KeyId=self._kms_key_id,
            Plaintext=plaintext.encode("utf-8"),
        )
        ciphertext_blob: bytes = response["CiphertextBlob"]
        return base64.b64encode(ciphertext_blob).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext string and return the original plaintext.

        Args:
            ciphertext: A base64-encoded string produced by :meth:`encrypt`.

        Returns:
            The original plaintext string.

        Raises:
            ValueError: If ``ciphertext`` is not valid base64.
            botocore.exceptions.ClientError: On KMS API errors.
        """
        try:
            ciphertext_blob = base64.b64decode(ciphertext, validate=True)
        except Exception as exc:
            raise ValueError(f"ciphertext is not valid base64: {exc}") from exc

        response = self._client.decrypt(CiphertextBlob=ciphertext_blob)
        plaintext_bytes: bytes = response["Plaintext"]
        return plaintext_bytes.decode("utf-8")
