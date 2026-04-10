#!/usr/bin/env python3
import argparse
import time

from app.services.signature import sign_payload


def main():
    parser = argparse.ArgumentParser(description="Generate checkin signature")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--session-id", type=int, required=True)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--ts", type=int, default=int(time.time()))
    args = parser.parse_args()

    sig = sign_payload(args.secret, args.session_id, args.user_id, args.nonce, args.ts)
    print(f"ts={args.ts}")
    print(f"signature={sig}")


if __name__ == "__main__":
    main()
