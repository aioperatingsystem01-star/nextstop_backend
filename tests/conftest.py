import os
import pytest

# Ensure tests run in isolated mock mode without connecting to live MongoDB Atlas
os.environ["TESTING"] = "1"
