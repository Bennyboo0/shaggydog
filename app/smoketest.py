"""Basic checks you can run locally to confirm wiring."""
from .auth import hash_password, verify_password

def main():
    h = hash_password("test123")
    assert verify_password("test123", h)
    assert not verify_password("wrong", h)
    print("OK: password hashing works")

if __name__ == "__main__":
    main()
