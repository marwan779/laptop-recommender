---
name: clean-architecture-solid
description: >-
  Enforces Clean Architecture (Domain, Repositories, Use Cases) and SOLID principles
  across all codebase modifications. Activate this skill whenever designing,
  implementing, or refactoring services, models, repositories, database operations,
  or business logic.
---

# Clean Architecture & SOLID Design Skill

This skill guides the design and implementation of new features, services, and refactoring to guarantee strict adherence to Clean Architecture and SOLID design principles.

---

## 1. Architectural Layers & Separation of Concerns

Every service (particularly in `catalog-service` and `scraper-service`) is organized into three strictly separated concentric rings:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Domain Layer (`app/domain/`)                             │
│    - Pure Python dataclasses, models, and domain services.  │
│    - Zero imports of SQLAlchemy, asyncpg, FastAPI, or httpx.│
│    - Contains business policies, mathematical formulas,     │
│      entity transitions, and validation rules.              │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│ 2. Application Layer (`app/services/`, `app/jobs/`)         │
│    - Orchestration use cases and scheduled jobs.            │
│    - Depends on domain services and repository interfaces.   │
│    - Contains NO SQL syntax and NO embedded business math.  │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│ 3. Infrastructure Layer (`app/repositories/`, `app/common/`)│
│    - SQLAlchemy queries, database sessions, S3 adapters.    │
│    - Encapsulates all data access and raw I/O.              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Standard Workflow for Any New Feature

When adding any new feature, always follow these 5 steps in order:

### Step 1: Define Domain Models & Pure Domain Service (`app/domain/`)
- Write pure Python dataclasses / Pydantic models for domain events, calculations, and entities.
- Implement domain logic as static/class methods or pure functions in a domain service (e.g., `PricingDomainService`, `SeederDomainService`).
- **Rule**: If a file in `app/domain/` imports SQLAlchemy, the build must fail.

### Step 2: Write Isolated Domain Unit Tests (`tests/test_<feature>_domain.py`)
- Test all edge cases, mathematical formulas, and business rules.
- Because domain code has zero I/O or DB dependencies, these tests must execute in $< 0.05\text{ seconds}$.

### Step 3: Implement Repositories (`app/repositories/`)
- Encapsulate all database queries, joins, and updates inside a dedicated repository subclassing `BaseRepository[ModelType]`.
- Keep queries focused and granular.
- Handle bulk updates or specialized watermarks inside the repository, not the service.

### Step 4: Implement Application Use Case (`app/services/` or `app/jobs/`)
- Inject repositories and the domain service.
- Fetch data from repositories $\rightarrow$ Pass data to domain service for calculation $\rightarrow$ Persist updated entities via repositories $\rightarrow$ Commit transaction.

### Step 5: Integration & Resilience Testing
- Test the end-to-end use case using the isolated `db_session` fixture (configured with `NullPool`).
- Test offline resilience and circuit breaker failure boundaries.

---

## 3. SOLID Checklist

Before approving or finalizing any code:

- [ ] **S (Single Responsibility)**: Does this class only have one reason to change? (e.g., repository only changes if schema/SQL changes; domain service only changes if business rules change).
- [ ] **O (Open/Closed)**: Are algorithms and extractors extensible via polymorphism or strategy pattern without editing core loops?
- [ ] **L (Liskov Substitution)**: Do all repository subclasses fulfill the `BaseRepository` contract without throwing unexpected errors?
- [ ] **I (Interface Segregation)**: Are interfaces small and focused rather than bloated?
- [ ] **D (Dependency Inversion)**: Do high-level services depend on domain abstractions and injected repositories rather than raw SQLAlchemy sessions and direct SQL queries?
