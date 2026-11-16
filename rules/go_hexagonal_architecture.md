# Go Hexagonal Architecture (Ports & Adapters) Rules

This rulebook defines architectural boundaries and guidelines for Go services following Hexagonal / Clean Architecture.

---

## 1. Architectural Layers & Boundaries

### Rule 1.1: Domain Isolation (Core Purity)
- **Severity:** `CRITICAL`
- **Requirement:** The core domain package (`internal/domain` or `pkg/domain`) must be pure Go with zero external transport or database dependencies.
- **Enforcement:**
  - No SQL drivers, ORMs, or database packages (`database/sql`, `gorm.io`, `github.com/jmoiron/sqlx`).
  - No HTTP or gRPC framework imports (`net/http`, `github.com/gin-gonic/gin`, `google.golang.org/grpc`).
  - Domain models must be pure Go structs; ports must be defined as Go `interface` types.

### Rule 1.2: Adapter Encapsulation
- **Severity:** `CRITICAL`
- **Requirement:** Driving adapters (HTTP handlers, gRPC servers, CLI) and driven adapters (database repositories, message brokers) must never bypass the application service/use-case layer.
- **Enforcement:**
  - HTTP handlers must not execute database queries or call external infrastructure adapters directly.
  - Handlers must interact solely via domain use-case or service interfaces.

### Rule 1.3: Concurrency & Goroutine Leaks
- **Severity:** `CRITICAL`
- **Requirement:** Never launch unbounded goroutines (`go func()`) without `context.Context` propagation or lifecycle cancellation tracking.
- **Enforcement:** All asynchronous workers must accept and respect `ctx.Done()`.

---

## 2. Go Conventions & Quality

### Rule 2.1: Explicit Error Handling
- **Severity:** `WARNING`
- **Requirement:** Never discard returned errors with blank identifier `_` unless explicitly justified (`_, _ = fmt.Fprintln(...)`).
- **Enforcement:** Always check `if err != nil` and wrap or return descriptive errors.

### Rule 2.2: Context Propagation
- **Severity:** `WARNING`
- **Requirement:** Function signatures performing I/O must accept `ctx context.Context` as the first argument.

