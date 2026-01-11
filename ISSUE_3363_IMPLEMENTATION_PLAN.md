# Issue #3363: Split Contributors Table - Implementation Plan

## Overview
Split the `contributors` table into two separate tables to eliminate data contention between GitHub/GitLab API tasks (core) and Git commit tasks (facade).

## Problem Analysis
- **Current Issue**: The `contributors` table stores both platform-specific data (gh_*, gl_* fields) AND git commit data (email, name)
- **Consequence**: When only one process runs, half the data is NULL
- **Root Cause**: Two independent processes (core & facade) compete to update the same table
- **Table Size**: One of the largest tables in Augur (migration concern)

---

## Proposed Schema Design

### Option 1: Core Identity + Platform Data Split

#### Table 1: `contributors` (Core Identity)
**Purpose**: Core contributor identity used by all systems
**Updated by**: Both core and facade tasks

```sql
CREATE TABLE augur_data.contributors (
    -- Primary Key
    cntrb_id UUID PRIMARY KEY DEFAULT nextval('augur_data.contributors_cntrb_id_seq'::regclass),
    
    -- Core Identity Fields (used by both processes)
    cntrb_login VARCHAR,              -- Generic login identifier
    cntrb_email VARCHAR,              -- Email from commit or API
    cntrb_full_name VARCHAR,          -- Full name
    cntrb_canonical VARCHAR,          -- Canonical email for matching
    cntrb_created_at TIMESTAMP(0),
    
    -- Company & Location
    cntrb_company VARCHAR,
    cntrb_location VARCHAR,
    cntrb_city VARCHAR,
    cntrb_state VARCHAR,
    cntrb_country_code CHAR(3),
    cntrb_long NUMERIC(11, 8),
    cntrb_lat NUMERIC(10, 8),
    
    -- Metadata
    cntrb_type VARCHAR,
    cntrb_fake SMALLINT DEFAULT 0,
    cntrb_deleted SMALLINT DEFAULT 0,
    cntrb_last_used TIMESTAMP WITH TIME ZONE,
    
    -- Audit fields
    tool_source VARCHAR,
    tool_version VARCHAR,
    data_source VARCHAR,
    data_collection_date TIMESTAMP(0) DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT "GL-cntrb-LOGIN-UNIQUE" UNIQUE (cntrb_login)
);
```

**Indexes for `contributors`**:
```sql
CREATE INDEX "cnt-fullname" ON augur_data.contributors USING hash (cntrb_full_name);
CREATE INDEX "cntrb-theemail" ON augur_data.contributors USING hash (cntrb_email);
CREATE INDEX "contributors_idx_cntrb_email3" ON augur_data.contributors (cntrb_email);
CREATE INDEX "cntrb_canonica-idx11" ON augur_data.contributors (cntrb_canonical);
CREATE INDEX "cntrb_login_platform_index" ON augur_data.contributors (cntrb_login);
CREATE INDEX "contributor_worker_email_finder" ON augur_data.contributors USING brin (cntrb_email);
CREATE INDEX "contributor_worker_fullname_finder" ON augur_data.contributors USING brin (cntrb_full_name);
CREATE INDEX "login" ON augur_data.contributors (cntrb_login);
CREATE INDEX "login-contributor-idx" ON augur_data.contributors (cntrb_login);
```

#### Table 2: `contributor_platform_data` (Platform-Specific)
**Purpose**: Store platform-specific API data from GitHub/GitLab
**Updated by**: Only core tasks (GitHub/GitLab API collection)

```sql
CREATE TABLE augur_data.contributor_platform_data (
    -- Primary Key
    platform_data_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Foreign Key to contributors
    cntrb_id UUID NOT NULL REFERENCES augur_data.contributors(cntrb_id) ON DELETE CASCADE,
    
    -- Platform identifier (github, gitlab, etc.)
    platform VARCHAR NOT NULL,
    
    -- GitHub-specific fields
    gh_user_id BIGINT,
    gh_login VARCHAR,
    gh_url VARCHAR,
    gh_html_url VARCHAR,
    gh_node_id VARCHAR,
    gh_avatar_url VARCHAR,
    gh_gravatar_id VARCHAR,
    gh_followers_url VARCHAR,
    gh_following_url VARCHAR,
    gh_gists_url VARCHAR,
    gh_starred_url VARCHAR,
    gh_subscriptions_url VARCHAR,
    gh_organizations_url VARCHAR,
    gh_repos_url VARCHAR,
    gh_events_url VARCHAR,
    gh_received_events_url VARCHAR,
    gh_type VARCHAR,
    gh_site_admin VARCHAR,
    
    -- GitLab-specific fields
    gl_id BIGINT,
    gl_username VARCHAR,
    gl_full_name VARCHAR,
    gl_web_url VARCHAR,
    gl_avatar_url VARCHAR,
    gl_state VARCHAR,
    
    -- Audit fields
    tool_source VARCHAR,
    tool_version VARCHAR,
    data_source VARCHAR,
    data_collection_date TIMESTAMP(0) DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints (one platform data record per contributor per platform)
    CONSTRAINT unique_cntrb_platform UNIQUE (cntrb_id, platform),
    CONSTRAINT "GH-UNIQUE-C" UNIQUE (gh_login) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT "GL-UNIQUE-B" UNIQUE (gl_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT "GL-UNIQUE-C" UNIQUE (gl_username) DEFERRABLE INITIALLY DEFERRED
);
```

**Indexes for `contributor_platform_data`**:
```sql
CREATE INDEX "gh_login" ON augur_data.contributor_platform_data USING btree (gh_login ASC NULLS FIRST);
CREATE INDEX "cpd_cntrb_id_idx" ON augur_data.contributor_platform_data (cntrb_id);
CREATE INDEX "cpd_gh_user_id_idx" ON augur_data.contributor_platform_data (gh_user_id);
CREATE INDEX "cpd_gl_id_idx" ON augur_data.contributor_platform_data (gl_id);
CREATE INDEX "cpd_platform_idx" ON augur_data.contributor_platform_data (platform);
```

---

## Migration Strategy

### Migration Approach: One-Shot Atomic Migration

**Advantages**:
- ✅ Completes in 2-6 hours (vs weeks of phased approach)
- ✅ Zero risk of incomplete migration
- ✅ Atomic operation (succeeds or rolls back cleanly)
- ✅ No code complexity supporting dual schemas
- ✅ Less total disk space needed than phased approach

**Steps**:
1. Create new `contributor_platform_data` table
2. Copy all platform-specific data from `contributors` to `contributor_platform_data`
3. Drop platform-specific columns from `contributors` table
4. Update all foreign key references and indexes
5. Verify data integrity

### Data Migration Logic

```sql
-- Step 1: Insert GitHub platform data (where gh_user_id is not null)
INSERT INTO augur_data.contributor_platform_data (
    cntrb_id, platform, 
    gh_user_id, gh_login, gh_url, gh_html_url, gh_node_id, gh_avatar_url, 
    gh_gravatar_id, gh_followers_url, gh_following_url, gh_gists_url, 
    gh_starred_url, gh_subscriptions_url, gh_organizations_url, gh_repos_url, 
    gh_events_url, gh_received_events_url, gh_type, gh_site_admin,
    tool_source, tool_version, data_source, data_collection_date
)
SELECT 
    cntrb_id, 'github',
    gh_user_id, gh_login, gh_url, gh_html_url, gh_node_id, gh_avatar_url,
    gh_gravatar_id, gh_followers_url, gh_following_url, gh_gists_url,
    gh_starred_url, gh_subscriptions_url, gh_organizations_url, gh_repos_url,
    gh_events_url, gh_received_events_url, gh_type, gh_site_admin,
    tool_source, tool_version, data_source, data_collection_date
FROM augur_data.contributors
WHERE gh_user_id IS NOT NULL;

-- Step 2: Insert GitLab platform data (where gl_id is not null)
INSERT INTO augur_data.contributor_platform_data (
    cntrb_id, platform,
    gl_id, gl_username, gl_full_name, gl_web_url, gl_avatar_url, gl_state,
    tool_source, tool_version, data_source, data_collection_date
)
SELECT 
    cntrb_id, 'gitlab',
    gl_id, gl_username, gl_full_name, gl_web_url, gl_avatar_url, gl_state,
    tool_source, tool_version, data_source, data_collection_date
FROM augur_data.contributors
WHERE gl_id IS NOT NULL;
```

---

## Code Changes Required

### 1. SQLAlchemy Models (`augur/application/db/models/augur_data.py`)

#### New Model: `ContributorPlatformData`
```python
class ContributorPlatformData(Base):
    __tablename__ = "contributor_platform_data"
    __table_args__ = (
        UniqueConstraint('cntrb_id', 'platform', name='unique_cntrb_platform'),
        UniqueConstraint('gh_login', name='GH-UNIQUE-C', initially="DEFERRED", deferrable=True),
        UniqueConstraint('gl_id', name='GL-UNIQUE-B', initially="DEFERRED", deferrable=True),
        UniqueConstraint('gl_username', name='GL-UNIQUE-C', initially="DEFERRED", deferrable=True),
        Index("gh_login", "gh_login"),
        Index("cpd_cntrb_id_idx", "cntrb_id"),
        Index("cpd_gh_user_id_idx", "gh_user_id"),
        Index("cpd_gl_id_idx", "gl_id"),
        Index("cpd_platform_idx", "platform"),
        {"schema": "augur_data"}
    )
    
    platform_data_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    cntrb_id = Column(UUID(as_uuid=True), ForeignKey('augur_data.contributors.cntrb_id', ondelete='CASCADE'), nullable=False)
    platform = Column(String, nullable=False)
    
    # GitHub fields
    gh_user_id = Column(BigInteger)
    gh_login = Column(String)
    # ... all other gh_* fields
    
    # GitLab fields
    gl_id = Column(BigInteger)
    gl_username = Column(String)
    # ... all other gl_* fields
    
    # Audit fields
    tool_source = Column(String)
    tool_version = Column(String)
    data_source = Column(String)
    data_collection_date = Column(TIMESTAMP(precision=0), server_default=text("CURRENT_TIMESTAMP"))
    
    # Relationship
    contributor = relationship("Contributor", back_populates="platform_data")
```

#### Update `Contributor` Model
- Remove all `gh_*` and `gl_*` columns
- Add relationship: `platform_data = relationship("ContributorPlatformData", back_populates="contributor")`

### 2. Data Parsing Functions (`augur/application/db/data_parse.py`)

#### Update `extract_needed_contributor_data()`
This function needs to return TWO dictionaries:
1. Core contributor data (for `contributors` table)
2. Platform data (for `contributor_platform_data` table)

```python
def extract_needed_contributor_data(contributor, tool_source, tool_version, data_source):
    if not contributor:
        return None, None
    
    cntrb_id = GithubUUID()
    cntrb_id["user"] = contributor["id"]
    
    # Core contributor data
    core_data = {
        "cntrb_id": cntrb_id.to_UUID(),
        "cntrb_login": contributor['login'],
        "cntrb_created_at": contributor['created_at'] if 'created_at' in contributor else None,
        "cntrb_email": contributor['email'] if 'email' in contributor else None,
        "cntrb_company": contributor['company'] if 'company' in contributor else None,
        "cntrb_location": contributor['location'] if 'location' in contributor else None,
        "cntrb_canonical": contributor['email'] if 'email' in contributor else None,
        "cntrb_last_used": None if 'updated_at' not in contributor else contributor['updated_at'],
        "cntrb_full_name": None if 'name' not in contributor else contributor['name'],
        "tool_source": tool_source,
        "tool_version": tool_version,
        "data_source": data_source
    }
    
    # Platform-specific data
    platform_data = {
        "cntrb_id": cntrb_id.to_UUID(),
        "platform": "github",
        "gh_user_id": contributor['id'],
        "gh_login": str(contributor['login']),
        "gh_url": contributor['url'],
        "gh_html_url": contributor['html_url'],
        "gh_node_id": contributor['node_id'],
        "gh_avatar_url": contributor['avatar_url'],
        "gh_gravatar_id": contributor['gravatar_id'],
        "gh_followers_url": contributor['followers_url'],
        "gh_following_url": contributor['following_url'],
        "gh_gists_url": contributor['gists_url'],
        "gh_starred_url": contributor['starred_url'],
        "gh_subscriptions_url": contributor['subscriptions_url'],
        "gh_organizations_url": contributor['organizations_url'],
        "gh_repos_url": contributor['repos_url'],
        "gh_events_url": contributor['events_url'],
        "gh_received_events_url": contributor['received_events_url'],
        "gh_type": contributor['type'],
        "gh_site_admin": contributor['site_admin'],
        "tool_source": tool_source,
        "tool_version": tool_version,
        "data_source": data_source
    }
    
    return core_data, platform_data
```

Similar updates needed for `extract_needed_gitlab_contributor_data()`.

### 3. Contributor Insertion Logic (`augur/application/db/lib.py`)

Update `batch_insert_contributors()` and related functions to insert into both tables:

```python
def batch_insert_contributors(contributors_data: List[dict], logger):
    """
    Insert contributors and their platform data
    
    Args:
        contributors_data: List of tuples (core_data, platform_data)
    """
    core_contributors = []
    platform_data_list = []
    
    for core_data, platform_data in contributors_data:
        if core_data:
            core_contributors.append(core_data)
        if platform_data:
            platform_data_list.append(platform_data)
    
    # Insert core contributors
    if core_contributors:
        bulk_insert_dicts(logger, core_contributors, Contributor, ["cntrb_id"])
    
    # Insert platform data
    if platform_data_list:
        bulk_insert_dicts(logger, platform_data_list, ContributorPlatformData, ["cntrb_id", "platform"])
```

### 4. Files Requiring Updates

Based on code analysis, these files reference contributor fields and need updates:

#### Core GitHub Tasks:
- `augur/tasks/github/pull_requests/core.py` - `process_pull_request_contributors()`
- `augur/tasks/github/pull_requests/tasks.py` - `process_pull_request_review_contributor()`
- `augur/tasks/github/issues.py` - Issue contributor processing
- `augur/tasks/github/events.py` - Event contributor processing
- `augur/tasks/github/messages.py` - Message contributor processing
- `augur/tasks/github/contributors.py` - Main contributor task

#### Facade GitHub Tasks:
- `augur/tasks/github/facade_github/tasks.py` - `process_commit_metadata()`
- `augur/tasks/github/facade_github/core.py`
- `augur/tasks/github/facade_github/contributor_interfaceable/contributor_interface.py`

#### GitLab Tasks:
- `augur/tasks/gitlab/issues_task.py`
- `augur/tasks/gitlab/merge_request_task.py`

#### Database Library:
- `augur/application/db/lib.py` - `batch_insert_contributors()`, `get_contributors_*()` functions
- `augur/application/db/data_parse.py` - All extract functions

#### API Layer:
- `augur/api/server.py` - GraphQL `ContributorType` may need to join platform data

---

## Testing Strategy

### 1. Pre-Migration Tests
```bash
# Capture current state
psql -d augur -c "SELECT COUNT(*) FROM augur_data.contributors;"
psql -d augur -c "SELECT COUNT(*) FROM augur_data.contributors WHERE gh_user_id IS NOT NULL;"
psql -d augur -c "SELECT COUNT(*) FROM augur_data.contributors WHERE gl_id IS NOT NULL;"
psql -d augur -c "SELECT COUNT(*) FROM augur_data.contributors WHERE gh_user_id IS NULL AND gl_id IS NULL;"
```

### 2. Migration Tests
```sql
-- Verify no data loss
SELECT 
    (SELECT COUNT(*) FROM augur_data.contributors) as total_contributors,
    (SELECT COUNT(*) FROM augur_data.contributor_platform_data WHERE platform = 'github') as github_count,
    (SELECT COUNT(*) FROM augur_data.contributor_platform_data WHERE platform = 'gitlab') as gitlab_count;

-- Verify all foreign keys are valid
SELECT COUNT(*) 
FROM augur_data.contributor_platform_data cpd
LEFT JOIN augur_data.contributors c ON cpd.cntrb_id = c.cntrb_id
WHERE c.cntrb_id IS NULL;
-- Should return 0

-- Verify unique constraints
SELECT gh_login, COUNT(*) 
FROM augur_data.contributor_platform_data 
WHERE gh_login IS NOT NULL 
GROUP BY gh_login 
HAVING COUNT(*) > 1;
-- Should return 0 rows
```

### 3. Integration Tests

Test each workflow:
- GitHub PR collection
- GitHub Issues collection
- Git commit collection (facade)
- GitLab data collection
- Contributor lookup by email
- Contributor lookup by login

### 4. Performance Tests

Compare query performance before/after:
```sql
-- Test 1: Get contributor with platform data
EXPLAIN ANALYZE
SELECT c.*, cpd.*
FROM augur_data.contributors c
LEFT JOIN augur_data.contributor_platform_data cpd ON c.cntrb_id = cpd.cntrb_id
WHERE c.cntrb_email = 'test@example.com';

-- Test 2: Get contributors by gh_login
EXPLAIN ANALYZE
SELECT c.*, cpd.*
FROM augur_data.contributors c
JOIN augur_data.contributor_platform_data cpd ON c.cntrb_id = cpd.cntrb_id
WHERE cpd.gh_login = 'testuser';
```

### 5. Rollback Plan

The migration script should include a complete `downgrade()` function:
1. Restore `gh_*` and `gl_*` columns to `contributors` table
2. Copy data back from `contributor_platform_data`
3. Drop `contributor_platform_data` table
4. Restore all original indexes and constraints

---

## Deployment Plan

### Phase 1: Preparation (Week 1)
- [ ] Review and finalize schema design
- [ ] Create migration script
- [ ] Update SQLAlchemy models
- [ ] Test migration on development database
- [ ] Create comprehensive test suite

### Phase 2: Code Updates (Week 2-3)
- [ ] Update data parsing functions
- [ ] Update insertion logic
- [ ] Update all GitHub/GitLab tasks
- [ ] Update facade tasks
- [ ] Update API layer
- [ ] Update all queries

### Phase 3: Testing (Week 4)
- [ ] Unit tests for all modified functions
- [ ] Integration tests for full workflows
- [ ] Performance testing
- [ ] Test with production-size dataset

### Phase 4: Deployment (Week 5)
- [ ] Backup production database
- [ ] Schedule maintenance window (4-8 hours)
- [ ] Run migration
- [ ] Verify data integrity
- [ ] Deploy updated code
- [ ] Monitor for issues

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss during migration | HIGH | Full database backup, transaction-based migration, verification queries |
| Migration takes too long | MEDIUM | Test on production-size dataset, optimize queries, prepare for extended window |
| Foreign key violations | MEDIUM | Pre-validate all references, use DEFERRED constraints |
| Performance degradation | MEDIUM | Add proper indexes, test queries before/after, optimize joins |
| Incomplete code updates | HIGH | Comprehensive grep for all contributor field references, thorough testing |
| Rollback complexity | HIGH | Detailed rollback procedure, test rollback on dev environment |

---

## Benefits After Implementation

✅ **No more data contention** between GitHub and facade tasks
✅ **No more partial NULL data** when only one process runs
✅ **Cleaner architecture** following normalization principles
✅ **Easier to extend** for new platforms (BitBucket, Gitea, etc.)
✅ **Better performance** with targeted indexes on platform data
✅ **Improved data integrity** with proper foreign keys

---

## Next Steps

1. ✅ Examine migration patterns (COMPLETED)
2. ✅ Draft schema design (COMPLETED)
3. ⏭️ Create Alembic migration script
4. ⏭️ Identify all code locations
5. ⏭️ Create test plan
