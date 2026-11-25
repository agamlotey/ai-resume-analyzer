from __future__ import annotations

import time
from functools import wraps

import jwt
from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import config


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class LocalAuth:
    kind = "local-jwt"

    def __init__(self, store):
        self.store = store

    def register(self, email, password, name):
        if self.store.get_user_by_email(email):
            raise AuthError("An account with this email already exists.", 409)
        self.store.create_user(email, name, generate_password_hash(password))

    def create_admin(self, email, password, name="Admin"):
        if not self.store.get_user_by_email(email):
            self.store.create_user(email, name, generate_password_hash(password), role="admin")

    def login(self, email, password):
        user = self.store.get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            raise AuthError("Incorrect email or password.", 401)
        payload = {"sub": user["id"], "email": user["email"], "name": user["name"], "role": user["role"],
                   "exp": int(time.time()) + 8 * 3600}
        return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")

    def verify(self, token):
        try:
            data = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise AuthError("Session expired. Please log in again.", 401)
        return {"id": data["sub"], "email": data["email"], "name": data.get("name"), "role": data["role"]}


class CognitoAuth:
    kind = "cognito"

    def __init__(self):
        import boto3
        self.client = boto3.client("cognito-idp", region_name=config.AWS_REGION)
        self.pool_id = config.COGNITO_USER_POOL_ID
        self.client_id = config.COGNITO_CLIENT_ID
        self.issuer = f"https://cognito-idp.{config.AWS_REGION}.amazonaws.com/{self.pool_id}"
        self.jwks = jwt.PyJWKClient(self.issuer + "/.well-known/jwks.json")

    def register(self, email, password, name):
        try:
            self.client.sign_up(ClientId=self.client_id, Username=email, Password=password,
                                UserAttributes=[{"Name": "email", "Value": email}, {"Name": "name", "Value": name}])
        except self.client.exceptions.UsernameExistsException:
            raise AuthError("An account with this email already exists.", 409)
        except self.client.exceptions.InvalidPasswordException as e:
            raise AuthError(e.response["Error"]["Message"], 400)

    def create_admin(self, email, password, name="Admin"):
        try:
            self.client.admin_create_user(UserPoolId=self.pool_id, Username=email, MessageAction="SUPPRESS",
                                          UserAttributes=[{"Name": "email", "Value": email},
                                                          {"Name": "name", "Value": name},
                                                          {"Name": "email_verified", "Value": "true"}])
        except self.client.exceptions.UsernameExistsException:
            pass
        self.client.admin_set_user_password(UserPoolId=self.pool_id, Username=email, Password=password, Permanent=True)
        self.client.admin_add_user_to_group(UserPoolId=self.pool_id, Username=email, GroupName="admin")

    def login(self, email, password):
        try:
            result = self.client.initiate_auth(ClientId=self.client_id, AuthFlow="USER_PASSWORD_AUTH",
                                               AuthParameters={"USERNAME": email, "PASSWORD": password})
        except (self.client.exceptions.NotAuthorizedException, self.client.exceptions.UserNotFoundException):
            raise AuthError("Incorrect email or password.", 401)
        return result["AuthenticationResult"]["IdToken"]

    def verify(self, token):
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            data = jwt.decode(token, key, algorithms=["RS256"], audience=self.client_id, issuer=self.issuer)
        except jwt.PyJWTError:
            raise AuthError("Session expired. Please log in again.", 401)
        role = "admin" if "admin" in data.get("cognito:groups", []) else "user"
        return {"id": data["sub"], "email": data.get("email"), "name": data.get("name"), "role": role}


def create_auth(store):
    if config.is_aws():
        return CognitoAuth()
    return LocalAuth(store)


def require_login(auth, admin=False):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify(error="Please log in first."), 401
            try:
                g.user = auth.verify(header[7:])
            except AuthError as e:
                return jsonify(error=str(e)), e.status
            if admin and g.user["role"] != "admin":
                return jsonify(error="Admin access required."), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator
