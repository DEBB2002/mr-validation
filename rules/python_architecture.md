# Python Clean Architecture & Design Guidelines

This rulebook defines architectural boundaries and best practices for Python backend applications (FastAPI, Flask, Django, etc.).

---

## 1. Architectural Layers & Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                     Presentation Layer                      │
│       (API Routers, FastAPI/Flask/Django Views, CLI)        │
└──────────────────────────────┬──────────────────────────────┘
                               │ calls
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                        Domain Layer                         │
│           (Entities, Value Objects, Domain Services)        │
└──────────────────────────────▲──────────────────────────────┘
                               │ implements / uses
┌──────────────────────────────┴──────────────────────────────┐
│                    Infrastructure / Data Layer              │
│       (SQLAlchemy ORM Models, DB Sessions, Repositories)    │
└─────────────────────────────────────────────────────────────┘
```

### Rule 1.1: Presentation Layer Boundaries
- **Severity:** `CRITICAL`
- **Requirement:** Presentation components (FastAPI routers, Flask/Django views, controllers, CLI commands) must **never** interact with database sessions (`SessionLocal`, `db.session`), raw database queries, or low-level ORM models (`SQLAlchemy`, `Django ORM`) directly.
- **Enforcement:** Routers/views must delegate all business logic and data operations to **Domain Services** or **UseCases**. Direct imports of database models or query building in router endpoints violate layer isolation.

### Rule 1.2: Domain Layer Purity
- **Severity:** `CRITICAL`
- **Requirement:** The Domain Layer (`domain/models.py`, `domain/services.py`, `domain/entities.py`) must remain pure Python.
- **Enforcement:**
  - Zero framework dependencies. Domain entities must **never** inherit from ORM base classes (e.g. `Base`, `declarative_base()`, `models.Model`).
  - No database annotations or column definitions (`Column(...)`, `relationship(...)`, `@Table`).
  - No framework-specific HTTP objects (`fastapi.Request`, `flask.Request`, `Response`).
  - Use pure dataclasses, Pydantic domain models (without ORM config), or standard Python classes.

### Rule 1.3: Data Layer Encapsulation & ORM Leakage
- **Severity:** `CRITICAL`
- **Requirement:** Infrastructure ORM models (SQLAlchemy / Tortoise / Peewee / Django) must remain strictly encapsulated within the Data/Infrastructure layer.
- **Enforcement:**
  - Repositories must map ORM entities to pure domain entities before returning them to domain services or API layers.
  - ORM instances with lazy-loading attributes must never be passed directly to API responses or domain logic.

---

## 2. Resource Management & Asynchronous Concurrency

### Rule 2.1: Asynchronous Event Loop Integrity
- **Severity:** `CRITICAL`
- **Requirement:** Inside asynchronous functions (`async def`), never invoke synchronous, blocking I/O calls.
- **Enforcement:**
  - Do not use `time.sleep()`; use `await asyncio.sleep()`.
  - Do not use synchronous HTTP clients like `requests.get()`; use asynchronous clients (`httpx.AsyncClient`, `aiohttp.ClientSession`).
  - Do not execute synchronous database drivers without `run_in_executor` or async ORM drivers (`asyncpg`, `async-session`).

### Rule 2.2: Database Session Scoping & Context Management
- **Severity:** `CRITICAL`
- **Requirement:** Database connections and sessions must always be managed via structured context managers (`with Session() as session:`) or dependency injection (e.g., FastAPI's `Depends(get_db)`).
- **Enforcement:** Never open global or unclosed database sessions that persist across HTTP requests or leak outside try/finally blocks.

---

## 3. Python Code Quality & Type Safety

### Rule 3.1: No Broad Exception Suppression
- **Severity:** `WARNING`
- **Requirement:** Avoid silent exception swallowing (`except Exception: pass`).
- **Enforcement:** Catch specific exceptions or log the exception stack trace before handling.

### Rule 3.2: Type Annotations on Public Interfaces
- **Severity:** `WARNING`
- **Requirement:** All public functions, service methods, and repository signatures should declare explicit argument and return type hints (`def get_user(user_id: int) -> Optional[User]:`).

### Rule 3.3: No Wildcard Imports
- **Severity:** `WARNING`
- **Requirement:** Avoid `from module import *`.
- **Enforcement:** Explicitly import needed symbols to maintain clear module dependency graphs and avoid namespace pollution.
