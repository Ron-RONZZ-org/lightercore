# AGENTS-exceptions.md — Exceptions Module

## Summary
Base exception hierarchy for all lightercore-based applications.

## Class Hierarchy
```
Exception
└── LighterbirdError          # Base — carries .message + .details kwargs
    ├── ConfigurationError    # Invalid/missing configuration
    ├── DatabaseError         # DB operation failure
    ├── DataError             # Data-layer errors (deleted entries)
    ├── AuthenticationError   # Credential/auth failure
    ├── SyncError             # Sync operation failure
    ├── AIError               # LLM provider failure
    └── ProtectedPathError    # Protected directory/file access
```

## Usage
Catch `LighterbirdError` at the top level for generic error handling. Subclass for domain-specific handling. Additional exception classes should be added here if they are needed by multiple downstream projects; project-specific exceptions should live in the project's own module.
