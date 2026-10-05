"""Generate a Web Push (VAPID) key pair, once per environment:

    python vapid.py

Put the two lines it prints in .env. VAPID_PUBLIC_KEY goes to browsers (via the API);
VAPID_PRIVATE_KEY signs pushes and must stay secret. Changing the pair later
invalidates every existing browser subscription, so keep it stable.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64(private), _b64(public)


if __name__ == "__main__":
    private, public = generate()
    print(f"VAPID_PRIVATE_KEY={private}")
    print(f"VAPID_PUBLIC_KEY={public}")
