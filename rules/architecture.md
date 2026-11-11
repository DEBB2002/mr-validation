# Android Clean Architecture & Language Guidelines

This document outlines the architectural compliance rules for Android merge requests (Kotlin & Java). All code changes must strictly adhere to these layer boundaries, lifecycle requirements, and language conventions.

---

## 1. Architectural Layers & Dependency Rule

Clean Architecture divides the codebase into three concentric layers. Dependencies must **only point inward**:
`Presentation Layer -> Domain Layer <- Data Layer`

### Rule 1.1: Presentation Layer Boundaries (Activities, Fragments, ViewModels, Composables)
- **CRITICAL Violation:** ViewModels, Activities, Fragments, or Composables must **never** call Data Layer components directly (e.g., Room DAOs, Retrofit API interfaces, database instances, network clients, or DataStore/SharedPreferences directly).
- **Required Pattern:** The Presentation layer must only communicate with the **Domain Layer** (UseCases/Interactors) or high-level repository interfaces defined in the Domain layer.
- **CRITICAL Violation:** Do not instantiate or access Room Database (`@Database`, `Room.databaseBuilder`, DAO objects) or network clients directly within Activities, Fragments, or ViewModels.

### Rule 1.2: Domain Layer Purity (Entities, UseCases, Repository Interfaces)
- **CRITICAL Violation:** The Domain layer must be pure Kotlin/Java and **must not import Android Framework dependencies** (`android.*`, `androidx.*`, `android.content.Context`, `android.os.*`, `android.view.*`).
  *(Exception: standard pure annotations like `javax.inject` or JSR-305 are allowed).*
- **CRITICAL Violation:** Domain Entities must not contain ORM or serialization annotations tied directly to persistence/transport frameworks (e.g., `@Entity`, `@ColumnInfo`, `@PrimaryKey` from Room, or `@Json`, `@SerializedName` if leaking framework models).
- **Rule:** Use Cases / Interactors must perform a single unit of business logic (usually with `operator fun invoke()`).

### Rule 1.3: Data Layer Encapsulation & Model Mapping
- **CRITICAL Violation:** Network Data Transfer Objects (DTOs) or local Room Entity classes must not be returned directly to the Presentation layer across the Domain boundary.
- **Required Pattern:** The Data layer must map internal database/network models to pure Domain models using dedicated mapper functions (e.g., `UserResponse.toDomain(): User`).

---

## 2. Android Lifecycle & Memory Leak Prevention

### Rule 2.1: No UI Context or View References in ViewModels or Long-Lived Singletons
- **CRITICAL Violation:** A `ViewModel`, Repository, or Singleton must **never** retain a reference to an Android `Context`, `Activity`, `Fragment`, `View`, or `Binding` object. This causes severe activity leaks across configuration changes.
- **Allowed Exception:** If an application context is strictly necessary (e.g., for system service lookup), use `AndroidViewModel(application)` with `getApplication<Application>()`, or inject the `ApplicationContext` via Hilt/Dagger (`@ApplicationContext context: Context`), never an `Activity` context.

### Rule 2.2: Safe Coroutine Lifecycles
- **CRITICAL Violation:** Never use `GlobalScope.launch` or unstructured coroutine scopes.
- **Required Pattern:**
  - In ViewModels, launch coroutines using `viewModelScope`.
  - In Activities/Fragments, launch coroutines using `lifecycleScope` or `viewLifecycleOwner.lifecycleScope.launch { repeatOnLifecycle(...) }`.

---

## 3. Kotlin Conventions & Reactive State

### Rule 3.1: Immutability and State Encapsulation
- **WARNING:** ViewModels must expose immutable state types (`StateFlow<T>`, `SharedFlow<T>`, or `LiveData<T>`) to the UI. The backing mutable state (`MutableStateFlow<T>`, `MutableLiveData<T>`) must be `private`.
  ```kotlin
  // GOOD:
  private val _uiState = MutableStateFlow<UiState>(UiState.Initial)
  val uiState: StateFlow<UiState> = _uiState.asStateFlow()

  // VIOLATION:
  val uiState = MutableStateFlow<UiState>(UiState.Initial) // Public mutable state
  ```

### Rule 3.2: Coroutine Dispatcher Injection
- **WARNING:** Do not hardcode dispatchers like `Dispatchers.IO` or `Dispatchers.Default` directly in Repositories or ViewModels. Inject a `CoroutineDispatcher` (or CoroutineDispatchers wrapper) to enable unit testability.

### Rule 3.3: Kotlin Null-Safety
- **WARNING:** Avoid using the force-unwrap operator `!!`. Use safe call operators (`?.`), Elvis operator (`?:`), `let`, or proper smart casting. Force-unwrapping introduces runtime `NullPointerException`s.

---

## 4. Java Conventions & Encapsulation

### Rule 4.1: Encapsulation & Field Exposure
- **WARNING:** Java classes should not have public mutable fields. Use private fields with proper getters and setters.

### Rule 4.2: Resource Cleanup
- **CRITICAL Violation:** Database Cursors, Input/Output Streams, and raw SQL handles in Java/Kotlin must be closed properly using `use` in Kotlin or `try-with-resources` in Java to prevent file descriptor leaks.

---

## Severity Summary

| Severity | Definition | Action |
|---|---|---|
| **CRITICAL** | Layer boundary crossing, direct DB/network calls in UI, memory leak (Context in ViewModel), Domain framework dependency, GlobalScope. | **Blocks MR merge (passed = False)** |
| **WARNING** | Hardcoded Dispatchers, public MutableStateFlow, unnecessary `!!` force unwrapping, missing encapsulation. | **Advisory (passed = True if no CRITICAL)** |

