# Issue #3363: Architecture Diagrams

## Current Architecture (Before Split)

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTRIBUTORS TABLE                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Core Identity Fields                                      │   │
│  │  • cntrb_id (PK)                                         │   │
│  │  • cntrb_email                                           │   │
│  │  • cntrb_full_name                                       │   │
│  │  • cntrb_login                                           │   │
│  │  • cntrb_canonical                                       │   │
│  │  • cntrb_location, company, etc.                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ GitHub Platform Fields (18 fields)                       │   │
│  │  • gh_user_id                                            │   │
│  │  • gh_login                                              │   │
│  │  • gh_url, gh_html_url, gh_node_id                      │   │
│  │  • gh_avatar_url, gh_gravatar_id                        │   │
│  │  • gh_followers_url, gh_following_url                   │   │
│  │  • gh_gists_url, gh_starred_url, etc.                   │   │
│  │  • gh_type, gh_site_admin                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ GitLab Platform Fields (6 fields)                        │   │
│  │  • gl_id                                                 │   │
│  │  • gl_username                                           │   │
│  │  • gl_full_name, gl_web_url                            │   │
│  │  • gl_avatar_url, gl_state                             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
           ▲                                    ▲
           │                                    │
    ┌──────┴────────┐                   ┌──────┴────────┐
    │ GitHub Tasks  │                   │  Facade Tasks │
    │  (Core API)   │                   │ (Git Commits) │
    │               │                   │               │
    │ Updates: ALL  │                   │ Updates: Core │
    │   fields      │                   │ fields + some │
    │               │                   │  gh_* fields  │
    └───────────────┘                   └───────────────┘
         
         ❌ PROBLEM: Both try to update the same table
         ❌ RESULT: Contention, locks, partial NULL data
```

---

## New Architecture (After Split)

```
┌───────────────────────────────────────┐
│      CONTRIBUTORS TABLE                │
│  (Core Identity - Shared)              │
│  ┌─────────────────────────────────┐  │
│  │ • cntrb_id (PK)                 │  │
│  │ • cntrb_email                   │  │
│  │ • cntrb_full_name               │  │
│  │ • cntrb_login                   │  │
│  │ • cntrb_canonical               │  │
│  │ • cntrb_location                │  │
│  │ • cntrb_company                 │  │
│  │ • cntrb_created_at              │  │
│  │ • cntrb_last_used               │  │
│  │ • Location fields (lat, long)   │  │
│  │ • Metadata (tool_source, etc.)  │  │
│  └─────────────────────────────────┘  │
└───────────────────────────────────────┘
           ▲                      │
           │                      │ (1:N relationship)
           │                      ▼
    ┌──────┴────────┐    ┌───────────────────────────────────────┐
    │ Facade Tasks  │    │  CONTRIBUTOR_PLATFORM_DATA TABLE      │
    │ (Git Commits) │    │  (Platform-Specific - API Only)       │
    │               │    │  ┌─────────────────────────────────┐  │
    │ Updates: Core │    │  │ • platform_data_id (PK)         │  │
    │ identity only │    │  │ • cntrb_id (FK)                 │  │
    └───────────────┘    │  │ • platform ('github'|'gitlab')  │  │
                         │  └─────────────────────────────────┘  │
                         │                                        │
                         │  ┌─────────────────────────────────┐  │
                         │  │ GitHub Fields (18)              │  │
                         │  │ • gh_user_id, gh_login          │  │
                         │  │ • gh_url, gh_html_url, etc.     │  │
                         │  └─────────────────────────────────┘  │
                         │                                        │
                         │  ┌─────────────────────────────────┐  │
                         │  │ GitLab Fields (6)               │  │
                         │  │ • gl_id, gl_username            │  │
                         │  │ • gl_web_url, gl_state, etc.    │  │
                         │  └─────────────────────────────────┘  │
                         └───────────────────────────────────────┘
                                         ▲
                                         │
                                   ┌─────┴──────┐
                                   │GitHub Tasks│
                                   │ (Core API) │
                                   │            │
                                   │Updates:    │
                                   │Platform    │
                                   │data only   │
                                   └────────────┘

         ✅ SOLUTION: Separate tables, no contention
         ✅ RESULT: Clean separation, no partial NULLs
```

---

## Data Flow Diagrams

### GitHub PR Collection (After Split)

```
┌──────────────────┐
│  GitHub API      │
│  (Pull Request)  │
└────────┬─────────┘
         │
         │ Fetch PR data with contributors
         ▼
┌────────────────────────────────────────┐
│ extract_needed_contributor_data()      │
│                                        │
│  Input: GitHub user object            │
│  {                                     │
│    "id": 123456,                      │
│    "login": "user",                   │
│    "email": "user@example.com",       │
│    "name": "User Name",               │
│    "url": "https://api.github...",    │
│    ... 15+ more fields                │
│  }                                     │
└────────┬───────────────────────────────┘
         │
         │ Splits into two dicts
         ▼
    ┌────────────────────────────────┐
    │  Returns: Tuple                │
    │  (core_data, platform_data)    │
    └────┬───────────────────┬───────┘
         │                   │
         │                   │
    ┌────▼───────────┐   ┌──▼─────────────────┐
    │  core_data     │   │  platform_data     │
    │  {             │   │  {                 │
    │   cntrb_id,    │   │   cntrb_id,        │
    │   cntrb_email, │   │   platform: "gh",  │
    │   cntrb_name,  │   │   gh_user_id,      │
    │   cntrb_login  │   │   gh_login,        │
    │  }             │   │   gh_url, ...      │
    └────┬───────────┘   │  }                 │
         │               └──┬─────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────┐   ┌──────────────────────┐
│  INSERT INTO    │   │  INSERT INTO         │
│  contributors   │   │  contributor_        │
│                 │   │  platform_data       │
└─────────────────┘   └──────────────────────┘

         │                  │
         │   Both linked by cntrb_id
         │                  │
         ▼                  ▼
     ┌───────────────────────────┐
     │  Database (Two Tables)    │
     │  Contributor + Platform   │
     └───────────────────────────┘
```

### Facade Commit Collection (After Split)

```
┌──────────────────┐
│  Git Repository  │
│  (git log)       │
└────────┬─────────┘
         │
         │ Parse commit data
         ▼
┌────────────────────────────────────────┐
│  Commit contains:                      │
│  {                                     │
│    "email": "dev@example.com",        │
│    "name": "Developer Name",          │
│    "commit_hash": "abc123..."         │
│  }                                     │
└────────┬───────────────────────────────┘
         │
         │ Try to match to existing contributor
         ▼
┌────────────────────────────────────────┐
│  Look up by email in contributors      │
│                                        │
│  If found: Use existing cntrb_id       │
│  If not found: Create new contributor  │
└────────┬───────────────────────────────┘
         │
         │ For NEW contributors only
         ▼
┌────────────────────────────────────────┐
│  Try to get GitHub login               │
│  (using GitHub API search by email)    │
│                                        │
│  If found: Get full GitHub user data   │
│  If not found: Continue without it     │
└────────┬───────────────────────────────┘
         │
         ├──────────────────┬─────────────┐
         │                  │             │
    Found GitHub        Not Found     Already
    User Data           GitHub        Exists
         │                  │             │
         ▼                  ▼             ▼
    ┌────────────┐     ┌────────────┐   ┌────────────┐
    │ Insert:    │     │ Insert:    │   │ Update:    │
    │ • Core to  │     │ • Core to  │   │ • Core in  │
    │   contrib  │     │   contrib  │   │   contrib  │
    │ • Platform │     │ • NO       │   │ • NO       │
    │   to       │     │   platform │   │   platform │
    │   platform │     │   data     │   │   change   │
    │   _data    │     │            │   │            │
    └────────────┘     └────────────┘   └────────────┘
```

---

## Query Pattern Changes

### Before: Direct Query

```sql
-- Old: Query single table
SELECT 
    cntrb_id,
    cntrb_email,
    cntrb_full_name,
    gh_login,           -- ← Was in same table
    gh_user_id          -- ← Was in same table
FROM 
    contributors
WHERE 
    gh_login = 'username';
```

### After: Join Query

```sql
-- New: Query with join
SELECT 
    c.cntrb_id,
    c.cntrb_email,
    c.cntrb_full_name,
    cpd.gh_login,       -- ← Now in platform_data
    cpd.gh_user_id      -- ← Now in platform_data
FROM 
    contributors c
JOIN 
    contributor_platform_data cpd 
    ON c.cntrb_id = cpd.cntrb_id
WHERE 
    cpd.gh_login = 'username' 
    AND cpd.platform = 'github';
```

---

## Relationship Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  CONTRIBUTORS (Parent)                                      │
│  ════════════════════════                                   │
│  • cntrb_id (UUID) ◄─────────────┐                         │
│  • cntrb_email                    │                         │
│  • cntrb_full_name                │                         │
│  • cntrb_login                    │  Foreign Key            │
│  • ...other core fields           │  Relationship           │
│                                    │  (1:N)                  │
└────────────────────────────────────┼─────────────────────────┘
                                     │
                                     │
                                     │
┌────────────────────────────────────┼─────────────────────────┐
│                                    │                         │
│  CONTRIBUTOR_PLATFORM_DATA (Child) │                         │
│  ══════════════════════════════════│═══════                  │
│  • platform_data_id (UUID)         │                         │
│  • cntrb_id (UUID) ────────────────┘                         │
│  • platform (VARCHAR) ◄── 'github' or 'gitlab'              │
│  • gh_user_id                                                │
│  • gh_login                                                  │
│  • gh_url                                                    │
│  • ...other GitHub fields                                    │
│  • gl_id                                                     │
│  • gl_username                                               │
│  • ...other GitLab fields                                    │
│                                                             │
│  CONSTRAINT: UNIQUE(cntrb_id, platform)                     │
│  → Each contributor can have ONE record per platform        │
│                                                             │
└─────────────────────────────────────────────────────────────┘


Example Data:
════════════

Contributors Table:
┌──────────────────────┬──────────────────┬─────────────────┐
│ cntrb_id             │ cntrb_email      │ cntrb_full_name │
├──────────────────────┼──────────────────┼─────────────────┤
│ 123e4567-e89b...     │ john@example.com │ John Smith      │
└──────────────────────┴──────────────────┴─────────────────┘

Contributor_Platform_Data Table:
┌──────────────────────┬──────────┬───────────┬─────────┐
│ cntrb_id             │ platform │ gh_login  │ gh_id   │
├──────────────────────┼──────────┼───────────┼─────────┤
│ 123e4567-e89b...     │ github   │ johnsmith │ 999999  │
│ 123e4567-e89b...     │ gitlab   │ jsmith_gl │ 888888  │
└──────────────────────┴──────────┴───────────┴─────────┘
                                    ▲
                                    │
                    Same person, multiple platforms!
```

---

## Index Strategy

### Contributors Table Indexes
```
┌─────────────────────────────────┐
│  contributors                   │
│  ═══════════════════            │
│                                 │
│  Indexes:                       │
│  • PRIMARY KEY (cntrb_id)       │
│  • HASH (cntrb_email)           │ ← Fast email lookup
│  • HASH (cntrb_full_name)       │ ← Fast name lookup
│  • BTREE (cntrb_email)          │ ← Range queries
│  • BTREE (cntrb_canonical)      │ ← Canonical matching
│  • BTREE (cntrb_login)          │ ← Login lookup
│  • BRIN (cntrb_email)           │ ← Sequential scans
│  • BRIN (cntrb_full_name)       │ ← Sequential scans
│                                 │
└─────────────────────────────────┘
```

### Contributor_Platform_Data Table Indexes
```
┌─────────────────────────────────┐
│  contributor_platform_data      │
│  ═══════════════════            │
│                                 │
│  Indexes:                       │
│  • PRIMARY KEY (platform_data_id)│
│  • BTREE (cntrb_id)             │ ← Join optimization
│  • BTREE (gh_user_id)           │ ← GitHub ID lookup
│  • BTREE (gh_login)             │ ← GitHub login lookup
│  • BTREE (gl_id)                │ ← GitLab ID lookup
│  • BTREE (platform)             │ ← Filter by platform
│                                 │
│  Unique Constraints:             │
│  • (cntrb_id, platform)         │ ← One per platform
│  • (gh_login)                   │ ← No duplicate logins
│  • (gl_id)                      │ ← No duplicate IDs
│                                 │
└─────────────────────────────────┘
```

---

## Performance Comparison

### Before Split (Single Table)

```
Query: Get contributor by gh_login
────────────────────────────────────────
SELECT * FROM contributors 
WHERE gh_login = 'user'

Execution:
• Seq Scan or Index Scan on contributors
• Time: ~5ms
• Contention: HIGH (table locked by facade)
```

### After Split (Two Tables)

```
Query: Get contributor by gh_login
────────────────────────────────────────
SELECT c.*, cpd.* 
FROM contributors c
JOIN contributor_platform_data cpd 
  ON c.cntrb_id = cpd.cntrb_id
WHERE cpd.gh_login = 'user'

Execution:
• Index Scan on contributor_platform_data (gh_login)
• Index Scan on contributors (cntrb_id)
• Nested Loop Join
• Time: ~7ms (slightly slower due to join)
• Contention: LOW (separate tables)

Net result: Better throughput despite slightly 
slower individual queries, because:
1. No table locking between GitHub and Facade
2. Smaller tables = better cache utilization
3. Platform-specific queries more efficient
```

---

## Migration Process Visualization

```
┌─────────────────────────────────────────────────────────┐
│ PHASE 1: BEFORE MIGRATION                               │
│ ════════════════════════════════                        │
│                                                         │
│  [contributors]                                         │
│    500,000 rows                                         │
│    • 50 columns (mixed core + platform)                │
│    • 250,000 have GitHub data                          │
│    • 50,000 have GitLab data                           │
│    • 200,000 have only core data                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         │
                         │ Run Migration
                         ▼
┌─────────────────────────────────────────────────────────┐
│ PHASE 2: DURING MIGRATION (Inside Transaction)         │
│ ═══════════════════════════════════════════════         │
│                                                         │
│  Step 1: Create contributor_platform_data table ✓      │
│  Step 2: Copy GitHub data → 250,000 rows inserted ✓    │
│  Step 3: Copy GitLab data → 50,000 rows inserted ✓     │
│  Step 4: Verify counts match ✓                         │
│  Step 5: Drop gh_*, gl_* columns from contributors ✓   │
│                                                         │
│  Duration: ~2-4 hours (depends on data size)           │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         │
                         │ Commit Transaction
                         ▼
┌─────────────────────────────────────────────────────────┐
│ PHASE 3: AFTER MIGRATION                                │
│ ════════════════════════════                            │
│                                                         │
│  [contributors]                      [contributor_      │
│    500,000 rows                      platform_data]     │
│    • 26 columns (core only)            300,000 rows     │
│    • Smaller table size                • 26 columns     │
│    • Faster scans                      • 250K GitHub    │
│                                        • 50K GitLab     │
│                                                         │
│  Total Storage: Similar or less                         │
│  Performance: Better (less contention)                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Summary: Why This Works

```
┌───────────────────────────────────────────────────────────┐
│                   KEY BENEFITS                            │
│ ═══════════════════════════════════════                   │
│                                                           │
│  1. SEPARATION OF CONCERNS                                │
│     ┌──────────────┐         ┌──────────────┐            │
│     │ Facade Tasks │         │ GitHub Tasks │            │
│     └──────┬───────┘         └──────┬───────┘            │
│            │                        │                     │
│            ▼                        ▼                     │
│     [contributors]          [platform_data]               │
│                                                           │
│     No more stepping on each other's toes!                │
│                                                           │
│  2. DATA INTEGRITY                                        │
│     • No partial NULL rows                                │
│     • Each table has complete data for its purpose        │
│     • Foreign keys ensure referential integrity           │
│                                                           │
│  3. SCALABILITY                                           │
│     • Easy to add new platforms (BitBucket, Gitea...)    │
│     • Just add more rows to platform_data                 │
│     • No schema changes to contributors table             │
│                                                           │
│  4. PERFORMANCE                                           │
│     • Smaller tables = better cache usage                 │
│     • Less contention = higher throughput                 │
│     • Targeted indexes on each table                      │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

This is a **textbook database normalization** example - taking a wide table with mixed concerns and splitting it into focused, single-responsibility tables!
