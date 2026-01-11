# Issue #3363: Test Plan for Contributors Table Split

## Overview
This document outlines the comprehensive testing strategy for validating the contributors table split migration.

---

## Test Environment Setup

### Prerequisites
1. Backup of production database (or production-size test database)
2. Test database with representative data size
3. Augur development environment configured
4. Access to GitHub/GitLab API tokens for testing

### Test Databases
- **Small Test DB**: 100 repos, ~1K contributors (for quick tests)
- **Medium Test DB**: 1K repos, ~10K contributors (for integration tests)
- **Large Test DB**: 10K+ repos, ~100K+ contributors (for performance tests)

---

## Phase 1: Pre-Migration Validation

### 1.1 Data Inventory
**Purpose**: Establish baseline metrics before migration

```sql
-- Record baseline statistics
CREATE TEMP TABLE pre_migration_stats AS
SELECT 
    'contributors_total' as metric,
    COUNT(*) as count
FROM augur_data.contributors
UNION ALL
SELECT 
    'contributors_with_github_data',
    COUNT(*)
FROM augur_data.contributors
WHERE gh_user_id IS NOT NULL
UNION ALL
SELECT 
    'contributors_with_gitlab_data',
    COUNT(*)
FROM augur_data.contributors
WHERE gl_id IS NOT NULL
UNION ALL
SELECT 
    'contributors_with_both',
    COUNT(*)
FROM augur_data.contributors
WHERE gh_user_id IS NOT NULL AND gl_id IS NOT NULL
UNION ALL
SELECT 
    'contributors_with_neither',
    COUNT(*)
FROM augur_data.contributors
WHERE gh_user_id IS NULL AND gl_id IS NULL
UNION ALL
SELECT 
    'unique_gh_logins',
    COUNT(DISTINCT gh_login)
FROM augur_data.contributors
WHERE gh_login IS NOT NULL
UNION ALL
SELECT 
    'unique_emails',
    COUNT(DISTINCT cntrb_email)
FROM augur_data.contributors
WHERE cntrb_email IS NOT NULL;

-- Save results
\copy (SELECT * FROM pre_migration_stats) TO '/tmp/pre_migration_stats.csv' CSV HEADER;
```

**Expected Results**: Document counts for validation after migration

### 1.2 Integrity Check
**Purpose**: Ensure current data has no major issues

```sql
-- Check for NULL primary keys
SELECT COUNT(*) as null_cntrb_ids
FROM augur_data.contributors
WHERE cntrb_id IS NULL;
-- Expected: 0

-- Check for duplicate gh_logins (should be caught by constraint but verify)
SELECT gh_login, COUNT(*) as count
FROM augur_data.contributors
WHERE gh_login IS NOT NULL
GROUP BY gh_login
HAVING COUNT(*) > 1;
-- Expected: 0 rows (or document exceptions)

-- Check foreign key references
SELECT COUNT(*) as orphaned_issues
FROM augur_data.issues i
LEFT JOIN augur_data.contributors c ON i.reporter_id = c.cntrb_id
WHERE c.cntrb_id IS NULL;
-- Expected: 0

SELECT COUNT(*) as orphaned_prs
FROM augur_data.pull_requests pr
LEFT JOIN augur_data.contributors c ON pr.pr_augur_contributor_id = c.cntrb_id
WHERE c.cntrb_id IS NULL;
-- Expected: 0
```

**Pass Criteria**: All checks return expected values

### 1.3 Performance Baseline
**Purpose**: Record current query performance for comparison

```sql
-- Test Query 1: Get contributor by email
EXPLAIN ANALYZE
SELECT * FROM augur_data.contributors
WHERE cntrb_email = 'test@example.com';

-- Test Query 2: Get contributor by gh_login
EXPLAIN ANALYZE
SELECT * FROM augur_data.contributors
WHERE gh_login = 'testuser';

-- Test Query 3: Get all GitHub contributors for a repo
EXPLAIN ANALYZE
SELECT DISTINCT c.*
FROM augur_data.contributors c
JOIN augur_data.commits cm ON c.cntrb_login = cm.cmt_author_platform_username
WHERE cm.repo_id = 1
AND c.gh_user_id IS NOT NULL;

-- Test Query 4: Count contributors by type
EXPLAIN ANALYZE
SELECT 
    COUNT(*) FILTER (WHERE gh_user_id IS NOT NULL) as github_users,
    COUNT(*) FILTER (WHERE gl_id IS NOT NULL) as gitlab_users
FROM augur_data.contributors;
```

**Expected Results**: Record execution times and query plans

---

## Phase 2: Migration Execution Tests

### 2.1 Migration Script Syntax Check
**Test**: Verify migration script has no syntax errors

```bash
cd /workspaces/augur
python -m augur.application.schema.alembic.env check
alembic check
```

**Pass Criteria**: No syntax errors

### 2.2 Dry Run on Small Test DB
**Test**: Run migration on small test database

```bash
# Backup small test DB
pg_dump -U augur -h localhost augur_test_small > /tmp/augur_test_small_backup.sql

# Run migration
cd /workspaces/augur
alembic upgrade head

# Check for errors in output
```

**Pass Criteria**: Migration completes without errors

### 2.3 Migration Data Validation
**Test**: Verify all data migrated correctly

```sql
-- Compare counts
WITH post_migration AS (
    SELECT 
        'contributors_total' as metric,
        COUNT(*) as count
    FROM augur_data.contributors
    UNION ALL
    SELECT 
        'platform_data_github',
        COUNT(*)
    FROM augur_data.contributor_platform_data
    WHERE platform = 'github'
    UNION ALL
    SELECT 
        'platform_data_gitlab',
        COUNT(*)
    FROM augur_data.contributor_platform_data
    WHERE platform = 'gitlab'
)
SELECT 
    p.metric,
    pr.count as pre_migration,
    p.count as post_migration,
    p.count - pr.count as difference
FROM post_migration p
JOIN pre_migration_stats pr ON p.metric LIKE pr.metric || '%'
OR (p.metric = 'platform_data_github' AND pr.metric = 'contributors_with_github_data')
OR (p.metric = 'platform_data_gitlab' AND pr.metric = 'contributors_with_gitlab_data');
```

**Pass Criteria**: 
- `contributors_total` unchanged
- `platform_data_github` = pre-migration `contributors_with_github_data`
- `platform_data_gitlab` = pre-migration `contributors_with_gitlab_data`

### 2.4 Data Integrity Post-Migration
**Test**: Verify data integrity after migration

```sql
-- Test 1: All platform_data records have valid cntrb_id
SELECT COUNT(*) as invalid_foreign_keys
FROM augur_data.contributor_platform_data cpd
LEFT JOIN augur_data.contributors c ON cpd.cntrb_id = c.cntrb_id
WHERE c.cntrb_id IS NULL;
-- Expected: 0

-- Test 2: No duplicate gh_logins
SELECT gh_login, COUNT(*) as count
FROM augur_data.contributor_platform_data
WHERE gh_login IS NOT NULL
GROUP BY gh_login
HAVING COUNT(*) > 1;
-- Expected: 0 rows

-- Test 3: Platform field is valid
SELECT platform, COUNT(*) 
FROM augur_data.contributor_platform_data
GROUP BY platform;
-- Expected: Only 'github' and 'gitlab'

-- Test 4: Contributors table no longer has platform fields
SELECT column_name 
FROM information_schema.columns 
WHERE table_schema = 'augur_data' 
AND table_name = 'contributors'
AND column_name LIKE 'gh_%' OR column_name LIKE 'gl_%';
-- Expected: 0 rows

-- Test 5: Check data sample matches
SELECT 
    c.cntrb_email,
    c.cntrb_full_name,
    cpd.gh_login,
    cpd.gh_user_id
FROM augur_data.contributors c
JOIN augur_data.contributor_platform_data cpd ON c.cntrb_id = cpd.cntrb_id
WHERE cpd.platform = 'github'
LIMIT 10;
-- Manually verify data looks correct
```

**Pass Criteria**: All tests pass

### 2.5 Index Verification
**Test**: Verify all indexes created correctly

```sql
-- Check indexes on contributor_platform_data
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'augur_data'
AND tablename = 'contributor_platform_data';
-- Expected: gh_login_idx, cpd_cntrb_id_idx, cpd_gh_user_id_idx, cpd_gl_id_idx, cpd_platform_idx

-- Check old indexes removed from contributors
SELECT indexname
FROM pg_indexes
WHERE schemaname = 'augur_data'
AND tablename = 'contributors'
AND indexname = 'gh_login';
-- Expected: 0 rows (index should be moved to platform_data)
```

**Pass Criteria**: All expected indexes exist, old ones removed

---

## Phase 3: Rollback Testing

### 3.1 Rollback Execution
**Test**: Verify rollback restores original state

```bash
# On test database after successful migration
cd /workspaces/augur
alembic downgrade -1  # Downgrade one revision
```

**Pass Criteria**: Downgrade completes without errors

### 3.2 Rollback Data Validation
**Test**: Verify data restored correctly

```sql
-- Check contributors table has gh_* fields back
SELECT column_name 
FROM information_schema.columns 
WHERE table_schema = 'augur_data' 
AND table_name = 'contributors'
AND column_name LIKE 'gh_%';
-- Expected: 18 rows (all gh_* fields)

-- Check platform_data table dropped
SELECT tablename
FROM pg_tables
WHERE schemaname = 'augur_data'
AND tablename = 'contributor_platform_data';
-- Expected: 0 rows

-- Verify data counts match original
SELECT COUNT(*) FROM augur_data.contributors;
SELECT COUNT(*) FROM augur_data.contributors WHERE gh_user_id IS NOT NULL;
-- Should match pre-migration stats

-- Sample data check
SELECT cntrb_email, cntrb_full_name, gh_login, gh_user_id
FROM augur_data.contributors
WHERE gh_login IS NOT NULL
LIMIT 10;
-- Manually verify data restored
```

**Pass Criteria**: All data and schema restored to pre-migration state

---

## Phase 4: Code Integration Tests

### 4.1 Unit Tests for Data Parsing

**Test File**: `tests/test_application/test_data_parse.py`

```python
def test_extract_needed_contributor_data_returns_tuple():
    """Test that extract_needed_contributor_data returns (core_data, platform_data)"""
    contributor = {
        'id': 123456,
        'login': 'testuser',
        'email': 'test@example.com',
        'name': 'Test User',
        # ... other GitHub fields
    }
    
    core_data, platform_data = extract_needed_contributor_data(
        contributor, 'test', '1.0', 'github'
    )
    
    assert core_data is not None
    assert platform_data is not None
    assert 'cntrb_id' in core_data
    assert 'cntrb_email' in core_data
    assert 'gh_user_id' in platform_data
    assert 'platform' in platform_data
    assert platform_data['platform'] == 'github'
```

**Run**: `pytest tests/test_application/test_data_parse.py -v`

### 4.2 GitHub PR Collection Test

**Test**: Collect PRs from a test repo and verify contributor data

```python
def test_github_pr_collection_with_split_tables():
    """Test GitHub PR collection creates records in both tables"""
    from augur.tasks.github.pull_requests.tasks import collect_pull_requests
    from augur.application.db.models import Contributor, ContributorPlatformData
    from augur.application.db.session import Session
    
    # Collect PRs from test repo
    result = collect_pull_requests.apply(args=[test_repo_id]).get()
    
    with Session() as session:
        # Check contributor created
        contributor = session.query(Contributor).filter_by(
            cntrb_email='testpr@example.com'
        ).first()
        
        assert contributor is not None
        
        # Check platform data created
        platform_data = session.query(ContributorPlatformData).filter_by(
            cntrb_id=contributor.cntrb_id,
            platform='github'
        ).first()
        
        assert platform_data is not None
        assert platform_data.gh_login is not None
        assert platform_data.gh_user_id is not None
```

**Run**: `pytest tests/test_tasks/test_github/test_pr_collection.py -v`

### 4.3 Facade (Git Commit) Collection Test

**Test**: Collect git commits and verify contributor matching works

```python
def test_facade_commit_collection_with_split_tables():
    """Test facade commit collection can still match/create contributors"""
    from augur.tasks.git.facade_tasks import process_commits
    from augur.application.db.models import Contributor, ContributorPlatformData
    from augur.application.db.session import Session
    
    # Process commits for test repo
    result = process_commits.apply(args=[test_repo_git_url]).get()
    
    with Session() as session:
        # Check contributor created with core data
        contributor = session.query(Contributor).filter_by(
            cntrb_email='commit@example.com'
        ).first()
        
        assert contributor is not None
        
        # May or may not have platform data (depends if GitHub lookup succeeded)
        platform_data_count = session.query(ContributorPlatformData).filter_by(
            cntrb_id=contributor.cntrb_id
        ).count()
        
        # Should be 0 or 1 (depending on whether GitHub user was found)
        assert platform_data_count in [0, 1]
```

**Run**: `pytest tests/test_tasks/test_git/test_facade.py -v`

### 4.4 Contributor Query Test

**Test**: Test querying contributors by various fields

```python
def test_get_contributor_by_github_user_id():
    """Test retrieving contributor by gh_user_id still works"""
    from augur.application.db.lib import get_contributors_by_github_user_id
    from augur.application.db.session import Session
    
    with Session() as session:
        contributors = get_contributors_by_github_user_id(session, 74832)
        
        assert len(contributors) > 0
        contributor = contributors[0]
        assert contributor.cntrb_id is not None
        
        # Check platform data accessible via relationship
        github_data = next(
            (pd for pd in contributor.platform_data if pd.platform == 'github'),
            None
        )
        assert github_data is not None
        assert github_data.gh_user_id == 74832
```

**Run**: `pytest tests/test_application/test_db_lib.py -v`

### 4.5 API GraphQL Test

**Test**: Test GraphQL API returns contributor data correctly

```python
def test_contributor_graphql_query():
    """Test GraphQL query for contributor with platform data"""
    query = """
    query {
        contributors(first: 5) {
            cntrb_id
            cntrb_email
            cntrb_full_name
            gh_login
            gh_user_id
        }
    }
    """
    
    result = execute_graphql_query(query)
    
    assert 'errors' not in result
    assert len(result['data']['contributors']) > 0
    
    contributor = result['data']['contributors'][0]
    assert 'cntrb_id' in contributor
    # gh_login and gh_user_id should be resolved from platform_data
    # May be null if contributor has no GitHub data
```

**Run**: `pytest tests/test_routes/test_graphql.py -v`

---

## Phase 5: Performance Testing

### 5.1 Query Performance Comparison

**Test**: Compare query performance before and after migration

```sql
-- Test on LARGE database

-- Query 1: Get contributor by email (should be same or better)
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM augur_data.contributors
WHERE cntrb_email = 'test@example.com';

-- Query 2: Get contributor with GitHub data (now requires join)
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.*, cpd.*
FROM augur_data.contributors c
LEFT JOIN augur_data.contributor_platform_data cpd 
    ON c.cntrb_id = cpd.cntrb_id AND cpd.platform = 'github'
WHERE c.cntrb_email = 'test@example.com';

-- Query 3: Get contributor by gh_login (now different table)
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.*, cpd.*
FROM augur_data.contributors c
JOIN augur_data.contributor_platform_data cpd 
    ON c.cntrb_id = cpd.cntrb_id
WHERE cpd.gh_login = 'testuser' AND cpd.platform = 'github';

-- Query 4: Get all contributors for repo commits
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT c.cntrb_id, c.cntrb_email, c.cntrb_full_name, cpd.gh_login
FROM augur_data.contributors c
LEFT JOIN augur_data.contributor_platform_data cpd 
    ON c.cntrb_id = cpd.cntrb_id AND cpd.platform = 'github'
JOIN augur_data.commits cm ON c.cntrb_login = cm.cmt_author_platform_username
WHERE cm.repo_id = 1;
```

**Pass Criteria**: 
- No query should be more than 2x slower than before
- Queries on core fields (email, name) should be same or faster
- Queries on platform fields (gh_login) may be slightly slower due to join but should still be fast with proper indexes

### 5.2 Insert Performance Test

**Test**: Measure contributor insertion performance

```python
import time
from augur.application.db.lib import batch_insert_contributors
from augur.application.db.session import Session

# Generate test data
test_contributors = []
for i in range(1000):
    core_data = {
        'cntrb_id': generate_uuid(),
        'cntrb_email': f'test{i}@example.com',
        'cntrb_login': f'testuser{i}',
        # ... other fields
    }
    platform_data = {
        'cntrb_id': core_data['cntrb_id'],
        'platform': 'github',
        'gh_user_id': 1000000 + i,
        'gh_login': f'testuser{i}',
        # ... other fields
    }
    test_contributors.append((core_data, platform_data))

# Time the insertion
with Session() as session:
    start = time.time()
    batch_insert_contributors(test_contributors, logger)
    session.commit()
    duration = time.time() - start
    
    print(f"Inserted 1000 contributors in {duration:.2f} seconds")
    # Expected: < 5 seconds for 1000 contributors
```

**Pass Criteria**: Batch insert of 1000 contributors completes in < 10 seconds

### 5.3 Full Collection Performance Test

**Test**: Run full collection cycle and measure time

```bash
# On medium-sized test database
time augur db collect --repo-group test_group --collection-phases core

# Record:
# - Total time
# - Number of contributors created
# - Number of platform_data records created
# - Any errors or warnings
```

**Pass Criteria**: 
- Collection completes successfully
- Time comparable to before migration (within 20%)
- No errors related to contributor insertion

---

## Phase 6: Load Testing

### 6.1 Concurrent Insertion Test

**Test**: Simulate multiple workers inserting contributors simultaneously

```python
from concurrent.futures import ThreadPoolExecutor
from augur.application.db.lib import batch_insert_contributors

def insert_batch(batch_id):
    """Insert a batch of test contributors"""
    contributors = generate_test_contributors(batch_id, 100)
    with Session() as session:
        batch_insert_contributors(contributors, logger)
        session.commit()
    return batch_id

# Run 10 workers in parallel, each inserting 100 contributors
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(insert_batch, i) for i in range(10)]
    results = [f.result() for f in futures]

# Verify no duplicates or constraint violations
```

**Pass Criteria**: 
- All insertions succeed
- No deadlocks or unique constraint violations
- 1000 unique contributors and 1000 platform_data records created

### 6.2 Table Contention Test

**Test**: Verify split tables reduce contention between GitHub and Facade tasks

```python
from concurrent.futures import ThreadPoolExecutor

def github_task_simulation():
    """Simulate GitHub API task updating platform data"""
    # Insert/update platform data for existing contributors
    pass

def facade_task_simulation():
    """Simulate Facade task updating core contributor data"""
    # Insert/update core contributor data (email, name)
    pass

# Run both task types concurrently
with ThreadPoolExecutor(max_workers=2) as executor:
    future1 = executor.submit(github_task_simulation)
    future2 = executor.submit(facade_task_simulation)
    
    future1.result()
    future2.result()

# Check for deadlocks or blocking
```

**Pass Criteria**: Both tasks complete without blocking each other

---

## Phase 7: Edge Cases & Error Handling

### 7.1 Null Platform Data Test

**Test**: Contributors with no platform data

```sql
-- Create contributor with only core data
INSERT INTO augur_data.contributors (
    cntrb_id, cntrb_email, cntrb_full_name, cntrb_login
) VALUES (
    gen_random_uuid(), 'noplatform@example.com', 'No Platform User', 'noplatform'
);

-- Verify query handles missing platform data
SELECT c.*, cpd.*
FROM augur_data.contributors c
LEFT JOIN augur_data.contributor_platform_data cpd ON c.cntrb_id = cpd.cntrb_id
WHERE c.cntrb_email = 'noplatform@example.com';
-- Should return contributor with NULL platform fields
```

**Pass Criteria**: Queries handle NULL platform data gracefully

### 7.2 Multiple Platform Test

**Test**: Contributor with both GitHub and GitLab data

```sql
-- Create contributor
INSERT INTO augur_data.contributors (
    cntrb_id, cntrb_email, cntrb_full_name, cntrb_login
) VALUES (
    'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX', 'multi@example.com', 'Multi Platform', 'multiuser'
);

-- Add GitHub platform data
INSERT INTO augur_data.contributor_platform_data (
    cntrb_id, platform, gh_user_id, gh_login
) VALUES (
    'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX', 'github', 999999, 'multiuser'
);

-- Add GitLab platform data
INSERT INTO augur_data.contributor_platform_data (
    cntrb_id, platform, gl_id, gl_username
) VALUES (
    'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX', 'gitlab', 888888, 'multiuser_gl'
);

-- Query both
SELECT c.cntrb_email, cpd.platform, cpd.gh_login, cpd.gl_username
FROM augur_data.contributors c
JOIN augur_data.contributor_platform_data cpd ON c.cntrb_id = cpd.cntrb_id
WHERE c.cntrb_email = 'multi@example.com';
-- Should return 2 rows, one for each platform
```

**Pass Criteria**: Contributor can have data for multiple platforms

### 7.3 Unique Constraint Test

**Test**: Verify unique constraints still work

```sql
-- Try to insert duplicate gh_login
INSERT INTO augur_data.contributor_platform_data (
    cntrb_id, platform, gh_user_id, gh_login
) VALUES (
    gen_random_uuid(), 'github', 111111, 'existinguser'
);

-- Try again with same gh_login
INSERT INTO augur_data.contributor_platform_data (
    cntrb_id, platform, gh_user_id, gh_login
) VALUES (
    gen_random_uuid(), 'github', 222222, 'existinguser'
);
-- Should fail with unique constraint violation
```

**Pass Criteria**: Duplicate gh_login/gl_id raises constraint error

---

## Phase 8: Production Readiness

### 8.1 Documentation Check
- [ ] Implementation plan reviewed
- [ ] Code changes documented
- [ ] Migration script commented
- [ ] Rollback procedure documented
- [ ] Known issues documented

### 8.2 Backup Verification
- [ ] Full database backup completed
- [ ] Backup tested (restore to separate instance)
- [ ] Backup storage verified (enough space, accessible)

### 8.3 Monitoring Setup
- [ ] Query performance monitoring enabled
- [ ] Error logging configured
- [ ] Alerting thresholds set
- [ ] Dashboard created for contributor tables

### 8.4 Deployment Checklist
- [ ] Maintenance window scheduled
- [ ] Stakeholders notified
- [ ] Rollback procedure tested
- [ ] Emergency contact list prepared
- [ ] Post-deployment validation scripts ready

---

## Test Results Summary Template

### Migration Execution
- **Database Size**: _____________
- **Migration Duration**: _____________
- **Contributors Migrated**: _____________
- **Platform Records Created**: _____________
- **Errors**: _____________
- **Warnings**: _____________

### Performance Results
- **Pre-Migration Avg Query Time**: _____________
- **Post-Migration Avg Query Time**: _____________
- **Performance Change**: _____________
- **Insert Performance**: _____________

### Test Pass/Fail
- [ ] Pre-migration validation: PASS / FAIL
- [ ] Migration execution: PASS / FAIL
- [ ] Data integrity: PASS / FAIL
- [ ] Rollback test: PASS / FAIL
- [ ] Unit tests: PASS / FAIL
- [ ] Integration tests: PASS / FAIL
- [ ] Performance tests: PASS / FAIL
- [ ] Load tests: PASS / FAIL
- [ ] Edge cases: PASS / FAIL

### Issues Identified
1. _____________
2. _____________
3. _____________

### Recommendations
1. _____________
2. _____________
3. _____________

---

## Success Criteria

The migration is considered successful if:

✅ All pre-migration data counts match post-migration counts
✅ No data loss detected in validation queries
✅ All foreign key relationships remain valid
✅ All unit tests pass
✅ All integration tests pass
✅ Query performance degradation < 20%
✅ Full collection cycle completes successfully
✅ No deadlocks or contention issues detected
✅ Rollback procedure works correctly
✅ All edge cases handled appropriately

---

## Sign-off

- **Test Lead**: _________________ Date: _______
- **Developer**: _________________ Date: _______
- **DBA**: _________________ Date: _______
- **Product Owner**: _________________ Date: _______
