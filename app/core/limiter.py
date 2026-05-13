"""Shared rate-limiter instance used across all route modules."""

import os
from slowapi import Limiter
from slowapi.util import get_remote_address

# Disable rate limiting in the test environment to prevent CI blocking
is_test = os.getenv("ENVIRONMENT") == "test"
limiter = Limiter(key_func=get_remote_address, enabled=not is_test)
