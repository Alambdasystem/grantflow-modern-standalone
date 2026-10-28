"""Standalone identities use existing User/Organization; credentials never leave the server."""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON
from db.database import Base


class AuthControl(Base):
    __tablename__ = 'auth_control'
    id = Column(Integer, primary_key=True)
    bootstrapped = Column(Boolean, nullable=False, default=False)


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    csrf_hash = Column(String(64), nullable=False)
    access_until = Column(Integer, nullable=False)
    absolute_until = Column(Integer, nullable=False)


class AuthRate(Base):
    __tablename__ = 'auth_rate_limits'
    key = Column(String(64), primary_key=True)
    attempts = Column(Integer, nullable=False, default=0)
    until = Column(Integer, nullable=False)


class AuthInvitation(Base):
    __tablename__ = 'auth_invitations'
    token_hash = Column(String(64), primary_key=True)
    email = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    reset_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    expires_at = Column(Integer, nullable=False)


class SchemaVersion(Base):
    __tablename__ = 'schema_versions'
    version = Column(Integer, primary_key=True)
    applied_at = Column(Integer, nullable=False)


class MigratedAccount(Base):
    """Explicit source-ID mapping; never infer an account link during login."""
    __tablename__ = 'auth_migrated_accounts'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    source_identity = Column(String(255), nullable=False)
    credential_source = Column(String(100), nullable=False)
    login_alias = Column(String(255), unique=True, nullable=True)
    permitted = Column(Boolean, nullable=False, default=False)
    role_ceiling = Column(String(20), nullable=False)
    scopes = Column(JSON, nullable=False, default=list)


class MigrationSafety(Base):
    __tablename__ = 'migration_safety'
    id = Column(Integer, primary_key=True)
    external_jobs_paused = Column(Boolean, nullable=False, default=True)
    source_cutoff = Column(String(100), nullable=False)


class AuthDelegation(Base):
    """Operator-approved, expiring data-owner delegation; never email linking."""
    __tablename__ = 'auth_delegations'
    delegate_user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    expires_at = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=False)
