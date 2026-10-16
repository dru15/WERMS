"""Local staff accounts and revocable, expiring opaque sessions."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from werms_api.operations import OperationError, Operations
from werms_api.schemas import AccountRequest


def password_digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


class Identity:
    def __init__(self, operations: Operations):
        self.operations = operations
        with operations.transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY, salt TEXT NOT NULL, digest TEXT NOT NULL,
                role TEXT NOT NULL, shelter_id TEXT, enabled INTEGER NOT NULL DEFAULT 1)""")
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                digest TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES accounts(username),
                expires_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT NOT NULL, peer TEXT NOT NULL, timestamp TEXT NOT NULL)""")

    @staticmethod
    def public(row) -> dict:
        return {k: row[k] for k in ("username", "role", "shelter_id", "enabled")}

    def accounts(self) -> list[dict]:
        with self.operations.transaction() as db:
            return [self.public(r) for r in db.execute("SELECT * FROM accounts ORDER BY username")]

    def create(self, request: AccountRequest, actor: str) -> dict:
        username = request.username.lower()
        if request.shelter_id and request.shelter_id not in {
            s["id"] for s in self.operations.network["shelters"]
        }:
            raise OperationError("UNKNOWN_SHELTER", "Choose a configured assembly site.", 422)
        salt = secrets.token_hex(16)
        digest = password_digest(request.password, salt)
        with self.operations.transaction() as db:
            if db.execute("SELECT 1 FROM accounts WHERE username=?", (username,)).fetchone():
                raise OperationError("ACCOUNT_EXISTS", "That username is already registered.")
            db.execute(
                "INSERT INTO accounts(username,salt,digest,role,shelter_id) VALUES (?,?,?,?,?)",
                (username, salt, digest, request.role, request.shelter_id),
            )
            self.operations._audit(
                db,
                "account.created",
                username,
                datetime.now(UTC),
                actor=actor,
                details={"role": request.role, "shelter_id": request.shelter_id},
            )
            return self.public(
                db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            )

    def login(self, username: str, password: str, peer: str) -> dict:
        username = username.lower()
        now = datetime.now(UTC)
        with self.operations.transaction() as db:
            cutoff = (now - timedelta(minutes=15)).isoformat()
            db.execute("DELETE FROM login_attempts WHERE timestamp<?", (cutoff,))
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (now.isoformat(),))
            count = db.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE username=? OR peer=?",
                (username, peer),
            ).fetchone()[0]
            if count >= 5:
                raise OperationError(
                    "LOGIN_THROTTLED", "Too many attempts. Retry in 15 minutes.", 429
                )
            row = db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            salt = row["salt"] if row else "0" * 32
            supplied = password_digest(password, salt)
            valid = row and row["enabled"] and secrets.compare_digest(supplied, row["digest"])
            if not valid:
                db.execute(
                    "INSERT INTO login_attempts VALUES (?,?,?)", (username, peer, now.isoformat())
                )
                # Commit the failure before returning the error; rollback would disable throttling.
                failure = True
            else:
                failure = False
                token = secrets.token_urlsafe(32)
                expires = (now + timedelta(hours=8)).isoformat()
                db.execute(
                    "INSERT INTO sessions VALUES (?,?,?)",
                    (
                        hashlib.sha256(token.encode()).hexdigest(),
                        username,
                        expires,
                    ),
                )
                self.operations._audit(db, "account.login", username, now, actor=username)
                result = {"token": token, "expires_at": expires, "user": self.public(row)}
        if failure:
            raise OperationError("INVALID_LOGIN", "Username or password is incorrect.", 401)
        return result

    def authenticate(self, token: str) -> dict:
        with self.operations.transaction() as db:
            row = db.execute(
                "SELECT a.* FROM sessions s JOIN accounts a ON s.username=a.username "
                "WHERE s.digest=? AND s.expires_at>? AND a.enabled=1",
                (hashlib.sha256(token.encode()).hexdigest(), datetime.now(UTC).isoformat()),
            ).fetchone()
            if not row:
                raise OperationError("SESSION_EXPIRED", "Sign in again to continue.", 401)
            return self.public(row)

    def logout(self, token: str):
        with self.operations.transaction() as db:
            db.execute(
                "DELETE FROM sessions WHERE digest=?", (hashlib.sha256(token.encode()).hexdigest(),)
            )

    def disable(self, username: str, actor: str):
        if username == actor:
            raise OperationError(
                "SELF_DISABLE", "Use another administrator to disable your account."
            )
        with self.operations.transaction() as db:
            row = db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            if not row:
                raise OperationError("ACCOUNT_NOT_FOUND", "Account was not found.", 404)
            db.execute("UPDATE accounts SET enabled=0 WHERE username=?", (username,))
            db.execute("DELETE FROM sessions WHERE username=?", (username,))
            self.operations._audit(db, "account.disabled", username, datetime.now(UTC), actor=actor)
