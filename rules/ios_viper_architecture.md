# iOS VIPER & Clean Architecture Rules

This rulebook defines architectural boundaries and conventions for iOS applications following VIPER (View, Interactor, Presenter, Entity, Router).

---

## 1. Architectural Layers & Boundaries

### Rule 1.1: View Boundary & Purity
- **Severity:** `CRITICAL`
- **Requirement:** Views / ViewControllers / SwiftUI Views must contain zero business logic and zero network or persistence calls.
- **Enforcement:**
  - Views must only capture user interactions and delegate them directly to their **Presenter**.
  - Views must never import or call `CoreData`, `SwiftData`, `URLSession`, or `Moya` directly.

### Rule 1.2: Presenter & Interactor Isolation
- **Severity:** `CRITICAL`
- **Requirement:** Presenters must not perform data fetching or business computations. They must delegate to **Interactors**.
- **Enforcement:**
  - Presenters format data for display; Interactors own use cases and communicate with repositories.
  - Presenters must hold a `weak` reference to their View to prevent retain cycles.

### Rule 1.3: Retain Cycles & Memory Leaks
- **Severity:** `CRITICAL`
- **Requirement:** Closures capturing `self` in asynchronous tasks or callbacks must explicitly use `[weak self]` to avoid memory leaks.

---

## 2. Swift Conventions & Safety

### Rule 2.1: Avoid Force Unwrapping
- **Severity:** `WARNING`
- **Requirement:** Avoid force-unwrapping optionals (`!`) and force-try (`try!`).
- **Enforcement:** Use `guard let`, `if let`, or nil-coalescing operator (`??`).
