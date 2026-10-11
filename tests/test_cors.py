import unittest

from app.main import app
from starlette.middleware.cors import CORSMiddleware


class CorsTests(unittest.TestCase):
    def test_local_and_production_frontend_origins_are_allowlisted(self):
        cors_middleware = next(
            middleware for middleware in app.user_middleware
            if middleware.cls is CORSMiddleware
        )
        allowed_origins = cors_middleware.kwargs["allow_origins"]
        self.assertEqual(
            allowed_origins,
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "https://ai-operations-agent-frontend.vercel.app",
            ],
        )
        self.assertNotIn("*", allowed_origins)


if __name__ == "__main__":
    unittest.main()
