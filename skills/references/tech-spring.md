# Spring Boot tech guide

## Architecture analysis checklist

- [ ] Layer structure: Controller → Service → Repository
- [ ] Where and how DTO ↔ Entity conversion happens
- [ ] Where business logic lives (Service vs domain model)
- [ ] Exception handling strategy (@ControllerAdvice, custom exceptions)
- [ ] Package structure: by layer vs by feature

## Database & JPA

- [ ] Entity design (associations, fetch strategy)
- [ ] Possible N+1 query problems
- [ ] @Transactional placement and attributes (readOnly, propagation)
- [ ] Possible LazyInitializationException
- [ ] Whether bulk operations are needed

## API design

- [ ] Follows RESTful principles (GET/POST/PUT/DELETE)
- [ ] Consistent URL naming (plural, kebab-case)
- [ ] Appropriate HTTP status codes
- [ ] Paging (Page vs Slice)
- [ ] Consistent error response structure

## Security

- [ ] @PreAuthorize / @Secured permission checks
- [ ] SQL injection defense (prepared statements)
- [ ] Input validation (@Valid, @Validated)
- [ ] Whether sensitive data is logged
- [ ] CORS configuration

## Implementation checklist

### Controller
- [ ] @RestController or @Controller (existing pattern)
- [ ] Consistent @RequestMapping paths
- [ ] DTO validation (@Valid, @Validated)
- [ ] Response format: ResponseEntity vs direct return

### Service
- [ ] Whether interfaces are split out (existing pattern)
- [ ] @Transactional placement and attributes
- [ ] Where DTO ↔ Entity conversion happens

### Repository
- [ ] JPA repository method naming (find vs get)
- [ ] Query methods vs @Query
- [ ] Whether a fetch join is needed

### DTO/Entity
- [ ] Lombok annotation pattern
- [ ] Whether the Builder pattern is used
- [ ] Validation annotations (@NotNull, @Size, and so on)

## Test patterns

| Test type | Annotation | Use |
|------------|-----------|------|
| Unit test | `@ExtendWith(MockitoExtension.class)` | Service logic |
| Controller test | `@WebMvcTest` | API endpoints |
| Repository test | `@DataJpaTest` | JPA queries |
| Integration test | `@SpringBootTest` | Full flow |

## Refactoring points

- **God service** → split services by responsibility
- **Conversion inside the controller** → move into a Mapper class
- **Complex query method names** → Specification or QueryDSL
- **Long parameter lists** → combine into a request DTO
