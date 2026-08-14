# -*- coding: utf-8 -*-
import time
import jwt

class JWTService:
    def __init__(self, secret):
        self.secret = secret

    def issue_token(self, user_entity, ttl_seconds=7 * 24 * 60 * 60):
        return self.issue_token_with_ttl(user_entity.id, user_entity.login, user_entity.email, ttl_seconds)

    def issue_token_with_ttl(self, user_id, login, email, ttl_seconds):
        now = int(time.time())
        payload = {
            "sub": user_id,
            "login": login,
            "email": email,
            "iat": now,
            "exp": now + ttl_seconds,
            "scopes": ["pos_config"],
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")
