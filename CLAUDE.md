# Claude Code Guidelines

This file contains guidelines for AI assistants (like Claude) working on this codebase.

## Code Quality Rules

### Type Annotations

**PROHIBITED: Do NOT use `# type: ignore` comments**

- Type ignore comments are not allowed in this codebase
- If you encounter type checking issues, fix the underlying problem instead
- Use proper type annotations and handle edge cases correctly
- If a third-party library has incomplete type stubs, contribute proper type hints rather than suppressing errors

### Why type: ignore is harmful

1. **Hides real bugs**: Type checkers exist to catch errors. Suppressing them defeats the purpose
2. **Technical debt**: Accumulates ignored type errors that may become harder to fix later
3. **Maintenance burden**: Future developers won't know why types were ignored
4. **False security**: Code may appear to work but contain hidden type mismatches

### Alternative approaches

Instead of `# type: ignore`, use:

- **Proper type annotations**: Add correct type hints to functions and variables
- **Type guards**: Use `isinstance()` checks to narrow types
- **Type casts**: Use `cast()` from `typing` module when you're certain of the type
- **Protocol types**: Define protocols for duck-typed interfaces
- **Generic types**: Use `TypeVar` and generics for flexible type-safe code
- **Stub files**: Create `.pyi` stub files for libraries without type information

## Example: Before and After

### Bad (PROHIBITED)
```python
result = some_function()  # type: ignore[return-value]
```

### Good
```python
from typing import cast

result = cast(ExpectedType, some_function())
# or better yet:
result: ExpectedType = some_function()
```

---

*This file should be updated as new code quality guidelines are established.*
